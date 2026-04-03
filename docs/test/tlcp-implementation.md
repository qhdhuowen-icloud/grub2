# iTrustMidware TLCP 可信启动度量实现说明

## 1. 架构概览

```
                    ┌─────────────────────────────────────┐
                    │          grub2-2.12 (EFI)            │
                    │                                       │
                    │  grub_cmd_boot()                      │
                    │    ├── grub_measure_configured_files()│  ← PCR 12 度量
                    │    ├── grub_tpm_policy_state()        │  ← 策略查询
                    │    └── grub_tpm_integrity_validation()│  ← 完整性校验
                    │             ↓                         │
                    │    kern/efi/tlcp.c (EFI TPM2 层)      │
                    └──────────────┬──────────────────────-─┘
                                   │ TPM2 命令
                    ┌──────────────▼────────────────────────┐
                    │         TPM 2.0 芯片                   │
                    │  NV 0x01800100  — 策略状态             │
                    │  Handle 0x81010101 — 硬件密钥(PCR 0-7) │
                    │  Handle 0x81010100 — 软件密钥(PCR 8-12)│
                    └───────────────────────────────────────┘
                                   ↑ 密钥封装
                    ┌──────────────┴────────────────────────┐
                    │         tlcptool (用户态)               │
                    │  deploy_audit_policy()                  │
                    │  deploy_supervisory_policy()            │
                    └───────────────────────────────────────┘
```

---

## 2. 策略类型

| 策略 | NV 值 | 行为 |
|------|-------|------|
| 审计策略 (audit)       | 1 | 完整性失败仅提示，可继续启动 |
| 监督策略 (supervisory) | 2 | 完整性失败时 `halt=1`，需要口令才能继续 |

---

## 3. 文件依赖

| 文件路径 | 写入方 | 读取方 | 内容 |
|---------|-------|-------|------|
| `/boot/policy.bin`           | tlcptool | GRUB | 策略类型（uint32_t，大端序） |
| `/boot/hardware_state.bin`   | tlcptool | GRUB | `[SHA256(key) \| AES-CBC(magic, key)]` |
| `/boot/software_state.bin`   | tlcptool | GRUB | 同上，软件密钥 |
| `/boot/hardware_passphrase.bin` | tlcptool | 用户 | 加密存储的硬件口令 |
| `/boot/software_passphrase.bin` | tlcptool | 用户 | 加密存储的软件口令 |
| `/boot/host_st_configure.xml`   | 管理员   | GRUB | 被度量到 PCR 12 的配置文件列表 |

---

## 4. PCR 绑定

```
PCR 0,1,2,3,6,7  →  硬件密钥 (handle 0x81010101)
                      度量内容：UEFI 固件、设备配置、安全启动状态

PCR 8,9,12       →  软件密钥 (handle 0x81010100)
                     度量内容：内核、initrd、GRUB 模块（PCR 8/9）
                               + host_st_configure.xml（PCR 12，GRUB 主动度量）
```

---

## 5. 状态文件格式

```
hardware_state.bin / software_state.bin：
  偏移 0   ：SHA256(dec_key)          — 32 字节
  偏移 32  ：AES-128-CBC(magic_str, dec_key, IV=0)

magic_str：
  硬件密钥文件："INSPUR__HARDWARE"（16 字节）
  软件密钥文件："INSPUR__SOFTWARE"（16 字节）

校验逻辑（GRUB 端）：
  1. TPM Unseal → dec_key
  2. SHA256(dec_key) ?= 文件前 32 字节
  3. AES-128-CBC 解密后 32 字节 ?= magic_str
```

---

## 6. 关键函数调用链

### 6.1 正常 TPM 路径

```
grub_cmd_boot()
  │
  ├─ grub_measure_configured_files()
  │     open /boot/host_st_configure.xml
  │     grub_tlcp_efi_measure(buf, len, PCR=12, "iTrustMidware:host_st_configure.xml")
  │         → EFI_TCG2_PROTOCOL.hash_log_extend_event()
  │
  ├─ grub_tpm_policy_state()
  │     check_tpm_policy_state()   ← TPM NV 查询
  │       │  失败
  │       └─ check_file_policy_state()  ← 读 /boot/policy.bin
  │
  └─ grub_tpm_integrity_validation(halt)
        get_hardware_enc_content()   ← 读 hardware_state.bin
        get_hardware_dec_key()
          │  StartAuthSession
          │  PolicyPCR(PCRs 0,1,2,3,6,7)
          │  Unseal(0x81010101)
          └─ FlushContext              ← 无论成功失败均执行
        validate_key_against_state()  ← SHA256 + AES 校验
        get_software_enc_content()
        get_software_dec_key()        ← PCRs 8,9,12 / handle 0x81010100
        validate_key_against_state()
        if (hard_fail || soft_fail) && halt:
            grub_file_integrity_validation(1)  ← 口令回退，仅调用一次
```

### 6.2 无 TPM 路径（i386-pc 或 TPM 不存在）

```
grub_cmd_boot()
  ├─ grub_measure_configured_files()   ← EFI 保护宏，非 EFI 平台跳过
  └─ grub_file_policy_state()          ← 读 /boot/policy.bin
       grub_file_integrity_validation(halt)  ← 口令校验循环
```

---

## 7. 新增/修改的源文件

```
grub-core/
  commands/boot.c              — 集成 TLCP 调用入口（+EFI 平台宏保护）
  kern/tlcp.c                  — 公开 API 实现（平台无关）
  kern/tlcp_aes.c              — AES-128-CBC 实现
  kern/tlcp_sha256.c           — SHA256 实现
  kern/efi/tlcp.c              — EFI 平台 TPM2 操作实现
  kern/efi/tpm2tis.c           — TPM2 TIS 驱动（去 efi_call 宏）
  kern/efi/tpm2nvstorage.c     — TPM2 NV 存储命令
  kern/efi/tpm2context.c       — TPM2 上下文管理
  kern/efi/tpm2enhancedauthorization.c
  kern/efi/tpm2getcapability.c
  kern/efi/tpm2integrity.c
  kern/efi/tpm2object.c
  kern/efi/tpm2session.c
  kern/efi/tpm2startup.c
  kern/efi/tpm2_util/          — TPM2 数据类型反序列化（23 个文件）

include/grub/
  tlcp.h                       — 公开 API 声明（EXPORT_FUNC 包裹，自包含）
  tlcp_aes.h
  tlcp_sha256.h
  tpm20.h                      — TCG TPM 2.0 数据类型定义
  efi/tlcp.h                   — 占位头（声明已移至 grub/tlcp.h）
  efi/tpm2tis.h
  efi/tpm2context.h
  efi/tpm2*.h                  — TPM2 各子命令头文件
```

---

## 8. 构建方法

```bash
# 在 grub2 spec 中已通过 Patch2001-Patch2009 应用所有 TLCP 修改
# 单文件合并 patch 位于 doc/tlcp-grub2-2.12.patch

# 构建 RPM
cd /root/rpmbuild
rpmbuild -bb SPECS/grub2.spec

# 生成 src.rpm
rpmbuild -bs SPECS/grub2.spec
```

---

## 9. 已修复的代码审查问题

| 编号 | 位置 | 问题 | 修复 |
|------|------|------|------|
| 1 | `kern/efi/tlcp.c:unmarshal_uint32` | 非对齐指针强转（未定义行为，ARM 上崩溃） | 改用 `grub_get_unaligned32()` |
| 2 | `kern/efi/tlcp.c:check_file_policy_state` | 文件不存在时 `grub_errno` 未清零（脏错误状态） | 添加 `grub_errno = GRUB_ERR_NONE` |
| 3 | `kern/efi/tlcp.c:get_hardware_dec_key` | Unseal 成功路径 `goto end` 跳过 FlushContext（TPM session 泄漏） | 移除 `goto end`，全路径经过 `flush:` 标签 |
| 4 | `kern/efi/tlcp.c:get_hardware_dec_key` | `out_data`（含密钥明文的栈变量）未清零 | flush 块中添加 `grub_memset(&out_data, 0, sizeof(out_data))` |
| 5 | `kern/tlcp.c:grub_tpm_integrity_validation` | 硬件和软件检查各自失败时分别调用口令回退（双重提示） | 合并为检查完成后的单次调用 |
| 6 | `kern/tlcp.c:grub_measure_configured_files` | `int len` 截断 64 位文件大小；`grub_file_read` 返回值类型不匹配 | 改为 `grub_size_t len = (grub_size_t)file->size` |
