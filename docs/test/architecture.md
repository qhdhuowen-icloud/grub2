# iTrustMidware 工程架构分析文档

版本：3.0.1 / 3.0.2（构建时间戳：202404192035）  
目标平台：Linux x86_64 / aarch64  
作者：浪潮（Inspur）

---

## 一、工程概述

**iTrustMidware** 是一套面向 Linux 系统的**可信计算中间件**。它基于 TPM 2.0 硬件安全芯片，提供以下核心能力：

- 系统完整性度量与基线管理（PCR 封存/解封）
- 可信引导事件日志解析（TCG 二进制格式）
- 审计策略与监督策略的部署与更新
- 度量数据的持久化存储（SQLite3）
- 可信报告导出（白名单比对）

其典型使用场景为：服务器在开机时通过 TPM 封存的密钥验证固件/软件状态是否被篡改，若不一致则拒绝解封密钥，从而实现可信引导（Trusted Boot）。

---

## 二、模块架构

工程分为两个独立的自动工具（Autotools）子模块，存在明确的层次依赖：

```
┌─────────────────────────────────────────────────────┐
│               TLCPTool（高层策略引擎）               │
│  libitrust.so  +  tlcptool（CLI工具）               │
├─────────────────────────────────────────────────────┤
│               TPMClient（低层 TPM 封装）             │
│  libtpmclient.so                                    │
├─────────────────────────────────────────────────────┤
│  libtss2-sys / libtss2-tcti  （TSS2 协议栈）        │
├─────────────────────────────────────────────────────┤
│  /dev/tpm0  （TPM 2.0 硬件设备）                   │
└─────────────────────────────────────────────────────┘
```

---

## 三、目录结构

```
iTrustMidware/
├── iTrustMidware.spec          # RPM 打包描述文件
├── CLAUDE.md                   # Claude Code 开发指引
├── TPMClient/                  # 模块一：低层 TPM 抽象层
│   ├── configure.ac            # 版本 3.0.2，依赖 tss2-sys, libcrypto
│   ├── include/
│   │   ├── tpmclient.h         # 公开 API（45 个函数签名）
│   │   └── tpmclient_common.h  # 公共类型、错误码枚举
│   └── src/
│       ├── tpmclient.c         # ~3000 行，TPM 操作核心实现
│       ├── tcti.c / tcti.h     # TCTI 设备抽象
│       ├── log.c / log.h       # 日志工具
│       └── error.h             # 错误处理宏
│
└── TLCPTool/                   # 模块二：高层策略与审计引擎
    ├── configure.ac            # 版本 3.0.2，依赖 tss2, libxml2, sqlite3, libcrypto
    ├── include/
    │   ├── itrust_midware.h    # 公开策略 API（11 个函数）
    │   └── itrust_midware_err.h # 错误码枚举（29 个错误类型）
    ├── src/
    │   ├── itrustmidware.c     # ~2400 行，核心策略逻辑
    │   ├── tpmmodule.c / .h    # TPM 模块初始化、策略加密
    │   ├── eventlog.c / .h     # TCG 事件日志解析
    │   ├── db.c / .h           # SQLite3 持久化接口
    │   ├── crypto.c / .h       # AES-CBC 加密/解密、随机数生成
    │   ├── sha256.c / .h       # SHA-256 纯 C 实现
    │   ├── sha1.c / .h         # SHA-1 实现
    │   ├── sm3.c / .h          # 国密 SM3 + HMAC
    │   ├── list.c / .h         # 侵入式双向链表（CCAN 风格）
    │   ├── util.c / .h         # 十六进制/字节转换、大端序工具
    │   ├── disk.c / .h         # GPT 分区检测
    │   ├── err.c / .h          # 错误码→字符串映射
    │   └── log.c / .h          # 日志框架（文件+宏）
    └── test/
        └── tlcptool.c          # ~600 行，CLI 管理工具入口
```

---

## 四、外部依赖

| 依赖库 | 版本要求 | 用途 |
|--------|---------|------|
| tpm2-tss (tss2-sys) | >= 2.0.0-4 | TSS2 系统 API，与 TPM 设备通信 |
| tss2-tcti-tabrmd | >= 2.0.0 | TPM 资源管理器接口（仅 TPMClient） |
| libcrypto (OpenSSL) | 通用 | AES 加密、RAND_bytes 随机数 |
| libxml2 | >= 2.9.1-5 | XML 配置文件解析（TLCPTool） |
| sqlite3 | 通用 | 度量数据持久化（TLCPTool） |
| autoconf | >= 2.69 | 构建系统生成 |

运行时还需要：
- `/dev/tpm0` — TPM 2.0 硬件设备
- `/sys/kernel/security/tpm0/binary_bios_measurements` — 内核提供的 TCG 事件日志

---

## 五、核心数据结构

### 5.1 TPMClient 模块

**错误码（tpmclient_common.h）：**
```c
enum TSS2_APP_RC_CODE {
    APP_RC_PASSED = 0,
    APP_RC_GET_NAME_FAILED,
    APP_RC_CREATE_SESSION_KEY_FAILED,
    // ... 共 40+ 种错误
    APP_RC_KEY_NOT_EXIST = 62
};
```

**密钥类型常量：**
```c
#define RSA_KEY      1   // RSA 存储密钥
#define SM2_KEY      2   // SM2 存储密钥
#define RSA_KEY_SIGN 4   // RSA 签名密钥
#define SM2_KEY_SIGN 5   // SM2 签名密钥
#define RSA_KEY_ENC  6   // RSA 加密密钥
#define SM2_KEY_ENC  7   // SM2 加密密钥
#define KEY_AES      8   // AES 对称密钥
#define KEY_SM4      9   // 国密 SM4 对称密钥

#define HANDLE_PERMANENT_SRK 0x81010008  // 持久存储根密钥 (SRK)
```

**全局状态：**
```c
TSS2_SYS_CONTEXT  *sysContext  = NULL;  // TSS2 系统上下文
TSS2_TCTI_CONTEXT *tctiContext = NULL;  // TCTI 设备上下文
```

### 5.2 TLCPTool 模块

**哈希摘要联合体（itrustmidware.c）：**
```c
typedef union digest {
    char sha1[41];    // 40 位十六进制 + null
    char sha256[65];  // 64 位十六进制 + null
    char sm3[65];     // 64 位十六进制 + null
    char buffer[1];   // 通用访问
} digest;
```

**度量日志节点（log_node）：**
```c
typedef struct log_node {
    char        *file_name;    // 事件/模块名称
    int          pcr_index;    // PCR 槽位索引（0-24）
    union digest hash;         // 摘要值
    struct log_node *next;     // 单向链表指针
} log_node;
```

**可信报告节点：**
```c
struct untrusted_report_node {
    char *name;        // 模块/文件名
    char *curr_value;  // 当前度量值
    char *base_value;  // 基线（白名单）期望值
    struct list_node list;
};
```

**策略状态枚举（tpmmodule.h）：**
```c
enum POLICY_STATE_CODE {
    POLICY_NOT_EXIST         = 0,  // 未部署策略
    AUDIT_POLICY_EXIST       = 1,  // 审计策略已激活（监控模式）
    SUPERVISORY_POLICY_EXIST = 2,  // 监督策略已激活（拦截模式）
};
```

**TCG 事件日志结构（eventlog.h）：**
```c
// v2 格式（支持多哈希算法）
typedef struct {
    unsigned int        pcr_index;   // PCR 槽位
    unsigned int        event_type;  // 固件/EFI 事件类型码
    TPML_DIGEST_VALUES  digests;     // 多算法摘要列表
    unsigned int        event_size;
    unsigned char       *event_data; // 可变长事件数据（GUID/字符串/二进制）
} tcg_pcr_event2;

// 哈希算法元数据
struct digest_info hashes[3] = {
    {0x0004, 0x14},  // SHA-1   (20 字节)
    {0x000b, 0x20},  // SHA-256 (32 字节)
    {0x0012, 0x20}   // SM3     (32 字节)
};
```

---

## 六、公开 API

### 6.1 TPMClient 公开 API（tpmclient.h，共 45 个函数）

| 分类 | 函数 | 说明 |
|------|------|------|
| 上下文管理 | `Tss2_Context_Initialize()` | 初始化 TPM 连接 |
| | `Tss2_Context_Finalize()` | 关闭 TPM 连接 |
| | `Tss2_Tpm_Client_Initialize()` | 客户端初始化（含算法检测） |
| | `Tss2_Tpm_Client_Finalize()` | 客户端清理 |
| 密钥操作 | `Tss2_CreatePrimary()` | 创建主密钥 |
| | `Tss2_CreateKey()` | 创建子密钥（带策略/授权） |
| | `Tss2_Load()` | 加载密钥到 TPM 会话 |
| | `Tss2_FlushContext()` | 从会话驱逐密钥 |
| | `Tss2_EvictControl()` | 将密钥持久化到 NV |
| 加密操作 | `Tss2_EncryptDecrypt()` | TPM 内对称加解密 |
| 封存/解封 | `Tss2_CreateSealedPrimary()` | 创建策略封存主密钥 |
| | `Tss2_Unseal()` | 解封（需 PCR 状态匹配） |
| PCR 操作 | `Tss2_PcrRead()` | 读取 PCR 值 |
| | `Tss2_PolicyPCR()` | 创建 PCR 策略 |
| 会话管理 | `Tss2_StartAuthSession()` | 开启策略/HMAC 会话 |
| | `Tss2_PolicyGetDigest()` | 获取策略摘要 |
| NV 存储 | `Tss2_NvDefineSpace()` | 定义 NV 空间 |
| | `Tss2_NvUndefineSpace()` | 删除 NV 空间 |
| | `Tss2_NvWrite()` | 写 NV 数据 |
| | `Tss2_NvRead()` | 读 NV 数据 |
| | `Tss2_NvReadPublic()` | 读 NV 公开属性 |
| 所有权 | `Tss2_TakeOwnerShip()` | 设置 TPM 层级认证 |
| | `Tss2_GetCapability()` | 查询 TPM 能力/属性 |
| | `Tss2_ReadPublic()` | 读取密钥公开部分 |
| 授权变更 | `Tss2_ChangeKeyAuth()` | 修改密钥授权 |
| | `Tss2_NvChangeAuth()` | 修改 NV 授权 |

### 6.2 TLCPTool 公开 API（itrust_midware.h，共 11 个函数）

```c
// 生命周期
int initialize_tlcp(void);      // 初始化 TPM 模块 + 数据库
int finalize_tlcp(void);        // 清理并关闭连接

// 策略状态
int check_policy_state(void);
// 返回: POLICY_NOT_EXIST / AUDIT_POLICY_EXIST / SUPERVISORY_POLICY_EXIST

// 审计策略（只读监控）
int deploy_audit_policy(void);     // 首次部署
int update_audit_policy(void);     // 刷新度量基线

// 监督策略（强制执行）
int deploy_supervisory_policy(void);
int update_supervisory_policy(void);

// 删除策略
int remove_policy(void);

// 导出密码短语（用于手工恢复）
int export_passphrase(
    unsigned char **software_passphrase, int *software_passphrase_len,
    unsigned char **hardware_passphrase, int *hardware_passphrase_len
);

// 可信报告（白名单比对结果）
int export_trusted_reports(struct trusted_report **reports, int *reports_num);
void free_trusted_reports(struct trusted_report *reports, int reports_num);
void iterator_trusted_reports(struct trusted_report *reports, int reports_num);

// 报告条目结构
struct trusted_report {
    char *name;   // 模块/文件名
    char *white;  // 白名单期望摘要
    char *curr;   // 当前实测摘要
};
```

### 6.3 错误码（itrust_midware_err.h）

```c
enum TSS2_APP_RESPONSE_CODE {
    TSS2_APP_RC_BAD_IO                    = 1,  // I/O 错误
    TSS2_APP_RC_BAD_NO_LICENSE            = 2,  // 缺少许可证
    TSS2_APP_RC_BAD_LICENSE_EXPIRED       = 3,  // 许可证过期
    TSS2_APP_RC_BAD_LICENSE               = 4,  // 无效许可证
    TSS2_APP_RC_BAD_NO_ABRMD_RUNNING      = 5,  // TPM 资源管理器未运行
    TSS2_APP_RC_OWNERSHIP_EXIST           = 6,  // TPM 已被占有
    TSS2_APP_RC_OWNERSHIP_NOT_EXIST       = 7,  // TPM 未被占有
    TSS2_APP_RC_BAD_OWNERAUTH_ERROR       = 8,  // TPM 所有者密码错误
    TSS2_APP_RC_BAD_HASH                  = 9,  // 无效哈希算法
    TSS2_APP_RC_BAD_PCR_BANK              = 10, // PCR 组不可用
    TSS2_APP_RC_BAD_POLICY_STATE          = 11, // 策略状态损坏
    TSS2_APP_RC_POLICY_NOT_EXIST          = 12, // 未部署策略
    TSS2_APP_RC_AUDIT_POLICY_EXIST        = 13, // 审计策略已存在
    TSS2_APP_RC_SUPERVISORY_POLICY_EXIST  = 14, // 监督策略已存在
    TSS2_APP_RC_BAD_NO_TRUST_LOG          = 15, // 事件日志缺失/为空
    TSS2_APP_RC_BAD_TRUST_LOG_CONTENT     = 16, // 事件日志格式错误
    TSS2_APP_RC_BAD_NO_TRUST_LOG_FILE     = 17, // 事件日志文件不存在
    TSS2_APP_RC_BAD_NO_ENC_FILE           = 18, // 加密状态文件缺失
    TSS2_APP_RC_BAD_NO_POLICY_STATE_FILE  = 19, // 策略状态文件缺失
    TSS2_APP_RC_BAD_KEY                   = 20, // 无效加密密钥
    TSS2_APP_RC_BAD_NO_PASSPHRASE_FILE    = 21, // 密码短语文件缺失
    TSS2_APP_RC_BAD_WHITE_LIST_CONTENT    = 22, // 白名单数据损坏
    TSS2_APP_RC_END                       = 23
};
```

---

## 七、核心工作原理

### 7.1 哈希算法优先级选择

系统初始化时自动检测 TPM 支持的算法，优先级为：

```
SM3（国密）> SHA-256 > SHA-1
```

选定后，所有度量操作均使用同一算法。

### 7.2 Owner 认证密钥推导

TPM 所有者密码从系统主板序列号派生：

```bash
dmidecode -t system | grep "Serial Number"
# 取前 1024 字节作为 owner_auth 输入
```

> 安全注意：若序列号可预测，此机制存在被攻击的风险。

### 7.3 策略部署完整流程

```
deploy_audit_policy()
│
├─ [事件日志] read_eventlog(/sys/kernel/security/tpm0/binary_bios_measurements)
│     └─ 解析 TCG v2 二进制格式 → eventlog_node 链表
│
├─ convert_eventlog_to_log(hash_alg, eventlog_list)
│     └─ 提取匹配算法的摘要 + 事件名 → log_node 链表
│
├─ add_measure_object(hash_alg, log_list)
│     └─ INSERT INTO {sha1|sha256|sm3}(pcr, name, content)
│              → /usr/local/KTrusted/data/log.db
│
├─ [密钥生成] create_rand() → RAND_bytes(seed=localtime)
│             create_key(rand)  → soft_key / hard_key
│
├─ [TPM 封存] deploy_audit_policy_module(owner_auth, soft_key, hard_key)
│     ├─ Tss2_StartAuthSession(TPM2_SE_POLICY)
│     ├─ Tss2_PolicyPCR(session, PCRs={0,1,2,3,6,7})
│     ├─ Tss2_PolicyGetDigest() → policy_hash
│     ├─ Tss2_CreateSealedPrimary(policy=policy_hash, data=soft_key)
│     └─ Tss2_EvictControl() → 持久化到 NV 句柄 0x81010100
│
├─ [加密存储] AES-CBC 加密 soft_key/hard_key 的哈希
│     ├─ /boot/software_state.bin（48 字节）
│     └─ /boot/hardware_state.bin（48 字节）
│
├─ [明文存储] 原始随机数写入
│     ├─ /boot/software_passphrase.bin（手工恢复用）
│     └─ /boot/hardware_passphrase.bin
│
├─ [NV 状态] Tss2_NvWrite(0x01800100, AUDIT_POLICY_EXIST)
│
└─ [文件状态] marshal_uint32 → /boot/policy.bin（4 字节）
```

### 7.4 PCR 封存机制

```
封存时（部署策略）：
  Policy = PCR(0|1|2|3|6|7) 的哈希匹配策略
  SealedKey = TPM_CreateSealedPrimary(data=key_material, policy=Policy)
  → 密钥以加密形式存储在 TPM NV（0x81010100 / 0x81010101）

解封时（下次开机）：
  if 当前 PCR(0|1|2|3|6,7) == 封存时的值:
      key = TPM_Unseal(SealedKey)   ← 成功，密钥明文返回
  else:
      TPM 拒绝解封                  ← 固件/引导被篡改，密钥不可用
```

PCR 0、1、2、3 度量 BIOS/UEFI 固件，PCR 6、7 度量启动选项和安全启动配置。任何一个变化都会导致解封失败。

### 7.5 可信报告生成原理

```
export_trusted_reports()
│
├─ 读取当前事件日志（实时度量值）
├─ 读取数据库中存储的基线值（部署时快照）
├─ 逐条比对 name → digest
├─ 不一致项：{name, curr_value, base_value} → untrusted_report_node
└─ 返回 trusted_report[] 数组给调用方
```

### 7.6 加密机制

```c
// AES-CBC 加密（OpenSSL），IV 全为 0
aes_encrypt(in, in_len, out, &out_len, key, key_len);
// key_len 必须为 16/24/32 字节（对应 AES-128/192/256）

// 注意：IV 固定为 0，若同一密钥加密多次，存在安全隐患
```

---

## 八、运行时文件

| 文件路径 | 大小 | 说明 |
|---------|------|------|
| `/boot/policy.bin` | 4 字节 | 策略状态码（大端序 uint32） |
| `/boot/hardware_state.bin` | 48 字节 | 硬件策略加密状态 |
| `/boot/software_state.bin` | 48 字节 | 软件策略加密状态 |
| `/boot/hardware_passphrase.bin` | 可变 | 硬件策略原始随机数（手工恢复用） |
| `/boot/software_passphrase.bin` | 可变 | 软件策略原始随机数 |
| `/boot/host_st_configure.xml` | 可变 | XML 度量配置 |
| `/usr/local/KTrusted/data/log.db` | SQLite3 | 度量数据库（sha1/sha256/sm3 三表） |
| `/var/log/iTrustMidware/tlcp/` | 日志 | TLCPTool 日志目录 |
| `/var/log/iTrustMidware/tpmclient/` | 日志 | TPMClient 日志目录 |

**TPM NV 索引：**
| 索引 | 说明 |
|------|------|
| `0x01800100` | POLICY_STATE_NV（10 字节，存策略状态） |
| `0x01800101` | TPM_OWNERPWDTEST_NV_INDEX（临时所有权验证） |

**TPM 持久密钥句柄：**
| 句柄 | 说明 |
|------|------|
| `0x81010100` | SOFTWARE_POLICY_KEY（软件策略封存密钥） |
| `0x81010101` | HARDWARE_POLICY_KEY（硬件策略封存密钥） |
| `0x81010008` | HANDLE_PERMANENT_SRK（存储根密钥） |

---

## 九、命令行工具（tlcptool）

安装路径：`/usr/bin/tlcptool`

| 参数 | 操作 |
|------|------|
| `-c` | 检测 TPM 设备（/dev/tpm0） |
| `-q` | 查询当前策略状态 |
| `-d` | 部署审计策略 |
| `-u` | 更新审计策略度量基线 |
| `-s` | 部署监督策略 |
| `-t` | 更新监督策略度量基线 |
| `-r` | 删除策略 |
| `-e` | 导出可信报告（当前值 vs 白名单） |

---

## 十、构建与安装

### 构建步骤

**TPMClient 模块：**
```bash
cd TPMClient
./bootstrap
./configure --prefix=<安装路径>
# 可选: --enable-debug  开启调试模式（-g -O0 -DDEBUG）
make clean && make && make install
```

**TLCPTool 模块（依赖 TPMClient 已安装）：**
```bash
cd TLCPTool
./bootstrap
./configure --enable-eventlog --prefix=<安装路径>
# --enable-eventlog: 启用 TCG 事件日志解析（编译宏 -DEVENTLOG）
make clean && make && make install
```

**RPM 打包：**
```bash
rpmbuild -ba iTrustMidware.spec
```

### 安装产物

| 类型 | 路径 |
|------|------|
| 共享库 | `/lib64/libtpmclient.so` |
| 共享库 | `/lib64/libitrust.so` |
| 静态库 | `<prefix>/lib/libtpmclient.a` |
| 静态库 | `<prefix>/lib/libitrust.a` |
| 可执行文件 | `/usr/bin/tlcptool` |
| 公开头文件 | `<prefix>/include/itrust_midware.h` |
| 公开头文件 | `<prefix>/include/itrust_midware_err.h` |

---

## 十一、已知技术债务与安全注意事项

| 项目 | 说明 |
|------|------|
| KDF 未实现 | `create_key()` 注释标注 "Todo: key = kdf(rand)"，当前为恒等函数 |
| AES IV 固定为 0 | 同一密钥多次加密可能泄露模式信息 |
| 许可证检查已禁用 | `#ifdef LICENSE` 代码段，运行时不强制执行 |
| Owner Auth 来源弱 | 从 dmidecode 序列号派生，若 SN 可预测则不安全 |
| 事件日志路径硬编码 | `/sys/kernel/security/tpm0/binary_bios_measurements`，部分系统可能不存在 |
| RPATH 被禁用 | RPM spec 通过 patch libtool 禁止硬编码 RPATH |

---

## 十二、数据流总图

```
                    ┌──────────────────────────────────────┐
                    │           系统启动（UEFI/BIOS）        │
                    └───────────────────┬──────────────────┘
                                        │ 度量固件/驱动/启动选项
                                        ▼
                    ┌──────────────────────────────────────┐
                    │  TPM PCR 0-7  +  内核事件日志          │
                    │  /sys/kernel/security/tpm0/           │
                    │  binary_bios_measurements             │
                    └───────────────────┬──────────────────┘
                                        │
                          ┌─────────────▼──────────────┐
                          │   iTrustMidware             │
                          │                             │
                          │   eventlog.c                │
                          │   (解析 TCG v2 二进制格式)   │
                          │          │                  │
                          │   itrustmidware.c           │
                          │   (策略逻辑/比对/封存)       │
                          │          │                  │
                          │   tpmmodule.c               │
                          │   (PCR 封存/解封)            │
                          │          │                  │
                          │   db.c → log.db             │
                          │   (度量基线持久化)           │
                          └─────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │     TPMClient               │
                         │     tpmclient.c             │
                         │     (TSS2 命令封装)          │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │  libtss2-sys / libtss2-tcti  │
                         └──────────────┬──────────────┘
                                        │
                         ┌──────────────▼──────────────┐
                         │       /dev/tpm0              │
                         │   （TPM 2.0 硬件芯片）        │
                         └─────────────────────────────┘

          状态持久化：
          ├─ /boot/policy.bin          ← 策略状态码
          ├─ /boot/software_state.bin  ← 加密密钥状态
          ├─ /boot/hardware_state.bin
          ├─ /boot/*_passphrase.bin    ← 恢复用随机数
          └─ NV 0x01800100             ← TPM 内策略状态
```

---

---

## 十三、与 GRUB2 及系统引导组件的关联关系

### 13.1 结论概述

iTrustMidware **不直接集成** GRUB2（无代码调用、无配置写入），但通过 **TPM PCR 度量机制**与 GRUB2 及整个 UEFI 引导链形成强耦合的**完整性验证关系**。

> 简言之：GRUB2 的行为决定 PCR 8/9/12 的值，而 iTrustMidware 的软件策略密钥正是封存在这三个 PCR 上。GRUB2 被篡改 → PCR 值改变 → 软件策略密钥无法解封。

---

### 13.2 PCR 分配与引导链对应关系

代码中有两套 PCR 组合，分别对应**硬件策略**和**软件策略**（`tpmmodule.c`）：

#### 硬件策略密钥（`create_hardware_key` / `update_hardware_key`）
```c
// tpmmodule.c:738, tpmmodule.c:827
int pcrnumber[9] = {0, 1, 2, 3, 6, 7, -1};
```

| PCR | 度量内容（TCG 规范） | 引导组件 |
|-----|-----------------|---------|
| PCR 0 | BIOS/UEFI 固件代码 | UEFI 固件本体 |
| PCR 1 | BIOS/UEFI 配置数据 | NVRAM 配置、SMBIOS |
| PCR 2 | Option ROM 代码 | 网卡/RAID 卡固件 |
| PCR 3 | Option ROM 配置 | 设备固件配置 |
| PCR 6 | 状态转换和唤醒事件 | S3/S4 休眠唤醒 |
| PCR 7 | Secure Boot 策略 | db、dbx、KEK、PK 证书库 |

**含义**：硬件策略绑定主板固件完整性。BIOS 升级、Option ROM 变更、Secure Boot 证书更新均会导致硬件策略密钥无法解封。

#### 软件策略密钥（`create_software_key` / `update_software_key`）
```c
// tpmmodule.c:560, tpmmodule.c:649
int pcrnumber[9] = {8, 9, 12, -1};
```

| PCR | 度量内容（TCG/GRUB2 规范） | 引导组件 |
|-----|----------------------|---------|
| PCR 8 | GRUB2 自身代码、加载的模块 | **grub2** |
| PCR 9 | 内核命令行参数、initrd | **grub2 → kernel** |
| PCR 12 | GRUB2 额外度量数据（或 shim） | **shim / grub2** |

**含义**：软件策略直接绑定 GRUB2 引导器完整性。GRUB2 被替换、模块被篡改、内核命令行被修改，均会导致软件策略密钥无法解封。

---

### 13.3 TCG 事件类型与 GRUB2 的关联

`eventlog.c` 中仅过滤 `IPL`（Initial Program Loader）类型的事件：

```c
// eventlog.c:154
static const unsigned int supported_event_types[1] = {IPL};
```

`IPL`（值=13）是 TCG 规范中专为**引导加载器**定义的事件类型。GRUB2 在执行过程中向 TPM 提交 IPL 事件，记录到 PCR 8/9，内容包括：
- GRUB2 二进制文件的哈希
- 加载的 `.mod` 模块哈希
- grub.cfg 内容
- 内核路径和命令行参数
- initrd 路径

iTrustMidware 解析事件日志时，正是通过匹配 `IPL` 事件提取 GRUB2 度量值，存入数据库作为软件基线。

此外，事件日志中还解析以下 EFI 事件（`eventlog.c:63-74`），这些均属于引导链度量：

| EFI 事件类型 | 含义 |
|------------|------|
| `EV_EFI_VARIABLE_BOOT` | UEFI 启动项变量（BootOrder、Boot0001 等） |
| `EV_EFI_BOOT_SERVICES_APPLICATION` | EFI 应用程序加载（shim.efi、grub.efi） |
| `EV_EFI_BOOT_SERVICES_DRIVER` | EFI 驱动加载 |
| `EV_EFI_GPT_EVENT` | GPT 分区表度量 |
| `EV_EFI_VARIABLE_DRIVER_CONFIG` | UEFI 驱动配置变量 |

---

### 13.4 历史版本曾使用 EFI 分区路径

`itrustmidware.c:23-28` 中注释掉的宏定义揭示了早期版本的设计：

```c
// itrustmidware.c（已注释，早期设计）
#define HARDWAREFILE  "/boot/efi/hardware_state.bin"
#define SOFTWAREFILE  "/boot/efi/software_state.bin"
#define HARDPASSPHRASE "/boot/efi/hardware_passphrase.bin"
#define SOFTPASSPHRASE "/boot/efi/software_passphrase.bin"
#define POLICYFILE    "/boot/efi/policy.bin"

// 当前使用（已改为普通 boot 分区）
#define HARDWAREFILE  "/boot/hardware_state.bin"
#define SOFTWAREFILE  "/boot/software_state.bin"
```

早期版本将状态文件存放在 EFI 系统分区（ESP，通常挂载于 `/boot/efi`）中，与 GRUB2 的 `/boot/efi/EFI/` 目录共处同一分区，耦合更为直接。当前版本改存至 `/boot`，与 GRUB2 部署目录仍在同一分区下。

---

### 13.5 完整引导链信任传递模型

```
上电
  │
  ▼
┌─────────────────────────────────────────┐
│  UEFI 固件（BIOS）                       │
│  度量自身到 PCR 0/1/2/3                  │
│  度量 Secure Boot 策略到 PCR 7           │
│  → 写入 /sys/.../binary_bios_measurements│
└──────────────────┬──────────────────────┘
                   │ 加载
                   ▼
┌─────────────────────────────────────────┐
│  shim.efi（可选，Secure Boot 场景）      │
│  EV_EFI_BOOT_SERVICES_APPLICATION 事件  │
│  度量 shim 自身到 PCR 4                  │
│  度量 grub.efi 到 PCR 12                │
└──────────────────┬──────────────────────┘
                   │ 加载
                   ▼
┌─────────────────────────────────────────┐
│  GRUB2 (grub.efi / grub2)              │
│  IPL 事件：度量自身模块到 PCR 8          │
│  IPL 事件：度量内核命令行/initrd 到 PCR 9│
│  读取 /boot/policy.bin 决定是否解封      │
└──────────────────┬──────────────────────┘
                   │ 加载
                   ▼
┌─────────────────────────────────────────┐
│  Linux 内核 + initrd                    │
│  启动 iTrustMidware 服务                 │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  iTrustMidware                          │
│  读取事件日志（含 GRUB2 的 IPL 事件）    │
│  对比数据库基线，生成可信报告            │
│  解封 TPM 密钥（需 PCR 0-3,6-7 匹配）   │
│           （需 PCR 8,9,12 匹配）         │
└─────────────────────────────────────────┘
```

**关键路径**：GRUB2 的每一次变更（升级、配置修改、模块替换）都会改变 PCR 8/9/12，导致软件策略密钥无法解封，系统无法获得受保护的密钥材料。

---

### 13.6 与 lkrg 内核模块的协同关系

同一仓库下存在 `lkrg`（Linux Kernel Runtime Guard）模块，其 systemd 服务配置（`lkrg/scripts/bootup/systemd/ktrusted.service`）表明 lkrg 也参与可信引导体系，在内核启动后加载，提供运行时内核完整性保护，与 iTrustMidware 的引导阶段度量形成互补：

| 阶段 | 组件 | 保护范围 |
|------|------|---------|
| 固件阶段 | UEFI + TPM PCR 0-7 | BIOS/固件完整性 |
| 引导加载器阶段 | GRUB2 + TPM PCR 8/9/12 | 引导器和内核命令行 |
| 内核启动后 | **iTrustMidware** | 度量基线比对、密钥解封 |
| 运行时 | **lkrg** | 内核符号/模块完整性监控 |

---

### 13.7 总结：与 GRUB2 的关联强度评级

| 关联维度 | 关联程度 | 说明 |
|---------|---------|------|
| 代码直接调用 | 无 | 不调用任何 grub2 API |
| PCR 封存依赖 | **强** | 软件密钥封存在 GRUB2 写入的 PCR 8/9/12 |
| 事件日志解析 | **强** | 专门过滤 IPL（引导加载器）事件类型 |
| 文件路径依赖 | 中 | 状态文件位于 /boot（同 GRUB2 部署目录） |
| 历史 EFI 路径 | 中 | 曾与 GRUB2 共用 /boot/efi 分区 |
| EFI 变量事件 | 中 | 解析 EV_EFI_VARIABLE_BOOT 等引导变量事件 |

---

*本文档由 Claude Code 自动分析生成，供其他 Claude 实例或开发者作为工程理解的基础输入。*
