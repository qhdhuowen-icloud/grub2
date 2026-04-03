# iTrustMidware + GRUB2 可信启动流程分析

> 本文档基于源码审计生成，经独立智能体交叉验证，结论可信度：核心流程 ✅ 正确，附注若干遗漏与缺陷。
>
> 分析日期：2026-04-02  
> 相关版本：grub2-2.02，iTrustMidware（见 iTrustMidware.spec）

---

## 一、架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│  tlcptool（iTrustMidware / TLCPTool）                             │
│  策略部署阶段（OS 正常运行时，管理员执行）                         │
│  deploy_audit/supervisory_policy()                                │
│    ├─ 读当前 PCR 值 → TPM PolicyPCR → 密封两把密钥到持久句柄      │
│    ├─ 生成 hardware_state.bin / software_state.bin               │
│    └─ 写 policy.bin + TPM NV 0x01800100                          │
└─────────────────────────┬────────────────────────────────────────┘
                          │  /boot/ 文件 + TPM 持久存储
                          ▼
┌──────────────────────────────────────────────────────────────────┐
│  GRUB2（启动阶段，grub-core/）                                    │
│  grub_cmd_boot()                                                  │
│    ├─ measure_configured_files()   ← 对配置文件度量，扩展 PCR     │
│    ├─ tpm_policy_state()           ← 检查是否已部署策略           │
│    └─ tpm/file_integrity_validation()  ← 校验完整性              │
│         └─ 失败 → 无限循环要求输入 硬密码 / 软密码               │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、策略部署阶段（tlcptool 侧）

### 2.1 密钥密封

管理员部署策略时，tlcptool 调用 `create_hardware_key()` 和 `create_software_key()`，将解密密钥**密封（Seal）**到 TPM。

| 密钥 | TPM 持久句柄 | 绑定的 PCR | 度量对象 |
|------|-------------|-----------|---------|
| HARDWARE_POLICY_KEY | `0x81010101` | PCR 0,1,2,3,6,7 | BIOS 固件、设备配置、安全启动配置 |
| SOFTWARE_POLICY_KEY | `0x81010100` | PCR 8,9,12 | Kernel、Initrd、GRUB 模块 |

**代码位置：**
- `TLCPTool/src/tpmmodule.c`：
  - `create_software_key()`：PCR 定义于第 560 行 `int pcrnumber[9]={8, 9, 12, -1};`
  - `create_hardware_key()`：PCR 定义于第 738 行 `int pcrnumber[9]={0, 1, 2, 3, 6, 7, -1};`
  - 两个句柄常量定义于第 14–15 行
  - NV 索引常量 `POLICY_STATE_NV = 0x01800100` 定义于第 13 行

### 2.2 状态文件生成

部署时生成三类文件，写入 `/boot/`：

#### `/boot/hardware_state.bin` 和 `/boot/software_state.bin`

文件格式（二进制拼接）：

```
[ 32 字节 SHA256(key) ] || [ AES-128-CBC(key, IV=0x00*16, "INSPUR__HARDWARE" 或 "INSPUR__SOFTWARE") ]
```

- 前 32 字节：密钥自身的 SHA256 摘要，用于 grub2 侧的密钥完整性校验
- 后半部分：用密钥 AES 加密的标识串，用于解密后验证

**代码位置：**
- `TLCPTool/src/itrustmidware.c`：`generate_enc_content()` 函数（约第 890–956 行）
  - 第 908 行：`sha256(soft_key, ..., soft_key_hash);`
  - 第 909 行：`memcpy(*soft_enc, soft_key_hash, sizeof(soft_key_hash));`
  - 第 921 行：`aes_encrypt(SOFTINFO, ..., *soft_enc + SHA256_DIGEST_LEN, ...);`
- 文件路径常量：第 30–31 行（`SOFTWAREFILE`、`HARDWAREFILE`）

#### `/boot/policy.bin`

4 字节大端整数，取值：

| 值 | 含义 |
|----|------|
| 1  | AUDIT_POLICY_EXIST — 审计策略（仅记录，不阻断） |
| 2  | SUPERVISORY_POLICY_EXIST — 监管策略（完整性失败则阻断） |

**代码位置：**
- `TLCPTool/src/itrustmidware.c`：`store_policy_state_file()` 函数（约第 844–862 行）
  - 第 857 行：`marshal_uint32(state_buf, (unsigned int)state);`
- 文件路径常量：第 34 行（`POLICYFILE`）

#### TPM NV `0x01800100`

同 `policy.bin` 相同的 4 字节策略类型值，写入 TPM NV 存储，作为 grub2 启动时优先读取的权威策略来源。

---

## 三、GRUB2 启动流程

### 3.1 入口：`grub_cmd_boot()`

**代码位置：** `grub-core/commands/boot.c:225–294`

执行顺序：

```
grub_cmd_boot()
  ├─ [1] measure_configured_files()           // boot.c:239
  ├─ [2] grub_tpm_chip_validate()             // boot.c:251  检测 TPM 是否存在
  │
  ├─ [TPM 存在]
  │   ├─ tpm_policy_state()                   // boot.c:253
  │   ├─ == POLICY_STATE_NONE → 跳过验证，直接启动
  │   ├─ AUDIT 模式 → tpm_integrity_validation(halt=0)   // boot.c:264
  │   └─ SUPERVISORY 模式 → tpm_integrity_validation(halt=1)  // boot.c:269
  │
  └─ [TPM 不存在]
      ├─ file_policy_state()                  // boot.c:284
      └─ AUDIT 或 SUPERVISORY → file_integrity_validation(1)  // boot.c:287
```

> **⚠️ 缺陷（审计发现）：** `file_integrity_validation()` 内部将 `halt` 参数以 `(void)halt` 忽略（`grub-core/kern/tlcp.c:724`），无论 AUDIT 还是 SUPERVISORY 模式，无 TPM 时均强制要求输入两个密码。

### 3.2 策略状态读取：`tpm_policy_state()`

**代码位置：** `grub-core/kern/tlcp.c:102–127`

```
tpm_policy_state()
  ├─ check_tpm_policy_state()          // 优先读 TPM
  │     ① GetCapability → TPMA_PERMANENT_OWNERAUTHSET 检查 TPM 所有权
  │     ② GetCapability → 句柄 0x81010100 是否存在
  │     ③ GetCapability → 句柄 0x81010101 是否存在
  │     ④ NV Read 0x01800100 → 读取4字节策略类型
  │   → 返回 AUDIT_POLICY_EXIST 或 SUPERVISORY_POLICY_EXIST
  │
  └─ [TPM 无策略] check_file_policy_state()  // fallback 到文件
        打开 /policy.bin，读取4字节，解析策略类型
```

**代码位置：**
- `check_tpm_policy_state()`：`grub-core/kern/efi/tlcp.c:68–194`
- `check_file_policy_state()`：`grub-core/kern/efi/tlcp.c:195–250`
- 返回值标志位：`include/grub/tlcp.h:31–36`
  - `POLICY_STATE_TPM_CHECK = 0x00010000`（bit16 置位表示来自 TPM）
  - `POLICY_STATE_AUDIT = 0x01`，`POLICY_STATE_SUPERVISORY = 0x02`

### 3.3 文件度量：`measure_configured_files()`

**代码位置：** `grub-core/kern/tlcp.c`（约第 1075–1120 行）

```
measure_configured_files()
  ├─ grub_get_devices()              // 枚举所有磁盘分区
  ├─ 搜索 /host_st_configure.xml
  ├─ grub_tpm_measure(config_file, GRUB_APPLICAION_PCR)  // 对配置文件本身度量
  └─ conf_parse()                    // 解析 XML，对其中每个条目调用 file_measure()
       └─ file_measure() → grub_tpm_measure(file, GRUB_APPLICAION_PCR)
```

度量结果（哈希）被扩展到 TPM PCR（对应 GRUB_APPLICAION_PCR），影响后续 `get_software_dec_key()` 时 PolicyPCR 的匹配结果。

> **🔍 遗漏（审计发现）：** `GRUB_APPLICAION_PCR` 的实际 PCR 编号未在 tlcp.c 中定义，需查阅 `include/grub/tpm.h`。

### 3.4 完整性校验（TPM 路径）：`tpm_integrity_validation()`

**代码位置：** `grub-core/kern/tlcp.c:631–712`

```
tpm_integrity_validation(halt)
  ├─ get_hardware_enc_content()  // 读 /hardware_state.bin
  ├─ get_software_enc_content()  // 读 /software_state.bin
  │
  ├─ tpm_hardware_integrity_validation(hard_buf)
  │     └─ get_hardware_dec_key()        // efi/tlcp.c:596–716
  │           ① get_tpm_supported_hash() // 选 SM3 > SHA256 > SHA1
  │           ② TPM2_StartAuthSession(SE_POLICY)
  │           ③ TPM2_PolicyPCR(session, PCR[0,1,2,3,6,7])
  │           ④ TPM2_Unseal(HARDWARE_POLICY_KEY=0x81010101)
  │              ├─ PCR 值未变 → Unseal 成功 → 返回解密密钥
  │              └─ PCR 值改变 → TPM 拒绝 → 返回 BAD_TRUST_STATE
  │         → validate_hardware_key(key, buf)
  │              ① SHA256(key) == buf[0:32] ?
  │              ② AES_decrypt(key, buf[32:]) == "INSPUR__HARDWARE" ?
  │   [失败且 halt=1] → file_hardware_integrity_validation()
  │
  └─ tpm_software_integrity_validation(soft_buf)
        └─ get_software_dec_key()        // efi/tlcp.c:717–818
              ① TPM2_PolicyPCR(session, PCR[8,9,12])
              ② TPM2_Unseal(SOFTWARE_POLICY_KEY=0x81010100)
        → validate_software_key(key, buf)
              ① SHA256(key) == buf[0:32] ?
              ② AES_decrypt(key, buf[32:]) == "INSPUR__SOFTWARE" ?
    [失败且 halt=1] → file_software_integrity_validation()
```

**各函数代码位置：**
- `get_hardware_dec_key()`：`grub-core/kern/efi/tlcp.c:596–716`（第 615 行定义 PCR）
- `get_software_dec_key()`：`grub-core/kern/efi/tlcp.c:717–818`（第 736 行定义 PCR）
- `validate_hardware_key()`：`grub-core/kern/tlcp.c:435–498`
- `validate_software_key()`：`grub-core/kern/tlcp.c:371–434`
- `get_hardware_enc_content()`：`grub-core/kern/efi/tlcp.c:252–300`
- `get_software_enc_content()`：`grub-core/kern/efi/tlcp.c:302–341`

### 3.5 密码输入（完整性校验失败后）

**代码位置：**
- 硬密码：`grub-core/kern/tlcp.c:565–628`（`file_hardware_integrity_validation()`）
- 软密码：`grub-core/kern/tlcp.c:500–563`（`file_software_integrity_validation()`）

```
file_*_integrity_validation(buf, buf_len)
  while(1):
    grub_printf("Enter hardware/software passphrase ")
    grub_password_get(passphrase, 32)      // 不回显输入
    convert_passphrase_to_key()            // hex 字符串 → 16字节 AES 密钥
    validate_*_key(key, buf)
      ├─ 正确 → "Passphrase is correct !!!" → break
      └─ 错误 → "Error passphrase wrong !!!" → continue（无限重试）
```

密码格式要求：
- 十六进制字符串，长度为偶数（每两个字符对应一个字节）
- 最大长度：32 字符（16 字节密钥）

**密码来源：** 部署策略时由 tlcptool 生成并保存到 `/boot/hardware_passphrase.bin` 和 `/boot/software_passphrase.bin`（iTrustMidware 侧的 `export_passphrase()` 接口对外提供）

---

## 四、触发密码输入的条件

| 触发原因 | 受影响的 PCR | 提示 | 典型场景 |
|---------|-------------|------|---------|
| BIOS/UEFI 固件升级 | PCR 0 | 硬密码 | 固件更新 |
| 主板配置变更（内存/设备） | PCR 1,3 | 硬密码 | 硬件变更 |
| 安全启动策略/证书变更 | PCR 6,7 | 硬密码 | 安全策略调整 |
| Kernel 镜像被替换 | PCR 8 | 软密码 | 内核升级或篡改 |
| Initrd 被替换 | PCR 9 | 软密码 | 系统初始化镜像变更 |
| GRUB 配置文件变更 | PCR 12 | 软密码 | 启动参数修改 |
| 无 TPM 芯片（纯文件模式） | — | 硬密码 + 软密码 | 无 TPM 硬件 |

---

## 五、状态文件校验逻辑（grub2 侧）

```
validate_software_key(key, key_len, buf, buf_len):
  key_hash = SHA256(key)
  ① if key_hash != buf[0:32]:  return -1   // 密钥完整性校验
  out = AES_CBC_decrypt(key, IV=0x00*16, buf[32:buf_len])
  ② if out[0:16] != "INSPUR__SOFTWARE":  return -1  // 标识串校验
  return 0  // 验证通过
```

AES 参数：
- 模式：AES-128-CBC
- 密钥长度：128 位（16 字节），不足时零填充（`create_key()` 函数，`grub-core/kern/tlcp.c:322–338`）
- IV：全零（`grub-core/kern/tlcp.c:257`）

---

## 六、整体流程图

```
系统启动
  │
  ▼ BIOS/UEFI 度量固件 → 扩展 PCR[0,1,2,3,6,7]
  │
  ▼ GRUB2 加载
  │   measure_configured_files()
  │   └─ 对 kernel/initrd/配置文件度量 → 扩展 PCR[8,9,12]
  │
  ▼ grub_cmd_boot() 执行
  │
  ├─ [无策略部署] ──────────────────────────────► 正常启动
  │
  ├─ [有策略 + 有TPM]
  │     │
  │     ▼ TPM PolicyPCR + Unseal
  │     ├─ PCR 值与部署时一致
  │     │     ├─ 硬件 Unseal 成功 → validate → 平台完整 ✅
  │     │     └─ 软件 Unseal 成功 → validate → 系统完整 ✅ ──► 正常启动
  │     │
  │     └─ PCR 值变化（内容被改变）
  │           ├─ 硬件 Unseal 失败
  │           │     └─ [SUPERVISORY] 打印 "Platform Integrity Has been Broken!"
  │           │                      → 无限循环要求输入 硬密码
  │           └─ 软件 Unseal 失败
  │                 └─ [SUPERVISORY] 打印 "Host OS Kernel&Initrd Has been Broken!"
  │                                  → 无限循环要求输入 软密码
  │           [AUDIT 模式] 仅打印警告，不阻断 ──────────────► 继续启动
  │
  └─ [有策略 + 无TPM]
        └─ 直接进入 file_integrity_validation()
              → 无条件要求输入 硬密码 + 软密码（halt 参数被忽略）
              → 密码正确后 ────────────────────────────────► 正常启动
```

---

## 七、审计发现的缺陷与遗漏

以下内容由独立审计发现，不影响核心流程正确性，但涉及安全性和健壮性：

### ⚠️ 缺陷1：`file_integrity_validation()` 的 `halt` 参数被忽略

**位置：** `grub-core/kern/tlcp.c:724`

`(void)halt;` 将参数废弃，无 TPM 场景下无论 AUDIT 还是 SUPERVISORY 模式，均强制要求输入密码。

### ⚠️ 缺陷2：AES-CBC 使用全零 IV

**位置：** `grub-core/kern/tlcp.c:257`

```c
const unsigned char iv[AES_BLOCK_SIZE] = {0x00, };
```

若相同密钥多次加密，全零 IV 会导致密文可预测，存在密码学安全风险。

### ⚠️ 缺陷3：密钥材料未清零释放

**位置：** `grub-core/kern/tlcp.c` 中各密码验证函数的 `end:` 标签处

密钥变量在 `grub_free()` 前未调用 `grub_memset(0)`，存在内存残留风险。

### 🔍 遗漏1：`GRUB_APPLICAION_PCR` 的实际编号未确认

`measure_configured_files()` 中度量扩展的目标 PCR 编号需查阅 `include/grub/tpm.h`，文档中 PCR 8/9/12 的对应关系需以该定义为准。

### 🔍 遗漏2：TPM NV 与 `/boot/policy.bin` 无同步机制

两者独立写入，若出现写入半成功，可能导致状态不一致，但不影响安全性（最坏情况是退化到文件模式）。

---

## 八、关键源文件索引

| 文件 | 职责 |
|------|------|
| `grub-core/commands/boot.c:225–294` | 启动命令入口，TLCP 验证总调度 |
| `grub-core/kern/tlcp.c:102–127` | 策略状态读取（TPM 优先，文件兜底） |
| `grub-core/kern/tlcp.c:631–712` | TPM 路径完整性验证主流程 |
| `grub-core/kern/tlcp.c:500–628` | 密码输入循环（软密码/硬密码） |
| `grub-core/kern/tlcp.c:371–498` | 密钥/密码验证逻辑（validate_*_key） |
| `grub-core/kern/efi/tlcp.c:68–194` | TPM 策略状态检查（NV/句柄检查） |
| `grub-core/kern/efi/tlcp.c:596–818` | TPM Unseal 流程（PCR 策略解封） |
| `include/grub/tlcp.h` | 错误码与策略状态标志位定义 |
| `TLCPTool/src/tpmmodule.c:555–750` | 策略部署侧：密钥创建与密封 |
| `TLCPTool/src/itrustmidware.c:844–956` | 策略部署侧：state 文件生成 |
