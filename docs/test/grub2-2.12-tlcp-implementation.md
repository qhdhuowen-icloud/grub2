# grub2-2.12 TLCP 可信启动度量实现说明

**版本**：1.0  
**日期**：2026-04-03  
**适用版本**：grub2-2.12  
**状态**：实现完成，编译通过

---

## 一、实现概述

本实现基于 grub2-2.12 原生架构，将 iTrustMidware 可信启动度量能力集成到 GRUB2 内核，实现与 tlcptool 工具的联动。

### 联动工作原理

```
┌──────────────────────────────────────────────────────────────┐
│  tlcptool（OS 运行时，管理员部署策略）                         │
│  deploy_audit/supervisory_policy()                            │
│    ├─ TPM2_Create + TPM2_Load → 持久化密钥                    │
│    │    硬件密钥 0x81010101 → 绑定 PCR 0,1,2,3,6,7           │
│    │    软件密钥 0x81010100 → 绑定 PCR 8,9,12                 │
│    ├─ 写 /boot/hardware_state.bin（SHA256+AES 加密载荷）      │
│    ├─ 写 /boot/software_state.bin（SHA256+AES 加密载荷）      │
│    ├─ 写 /boot/policy.bin（策略类型：1=审计 2=监督）          │
│    └─ 写 TPM NV 0x01800100（策略状态元数据）                  │
└────────────────────────────┬─────────────────────────────────┘
                             │ /boot/ 文件 + TPM 持久存储
                             ▼
┌──────────────────────────────────────────────────────────────┐
│  GRUB2 启动阶段（grub-core/commands/boot.c）                  │
│  grub_cmd_boot()                                              │
│    ├─ grub_measure_configured_files()                         │
│    │    └─ 读 /boot/host_st_configure.xml → 扩展 PCR 12      │
│    ├─ grub_tpm_policy_state()                                 │
│    │    ├─ 查 TPM NV 0x01800100 → 确认策略类型                │
│    │    └─ 降级：读 /boot/policy.bin                          │
│    └─ 完整性校验：                                            │
│         有 TPM + Audit   → grub_tpm_integrity_validation(0)  │
│         有 TPM + 监督    → grub_tpm_integrity_validation(1)  │
│         无 TPM / 降级    → grub_file_integrity_validation(1) │
└──────────────────────────────────────────────────────────────┘
```

### TPM2 Unseal 四步序列

```
1. grub_tpm2_start_auth_session()   建立 Policy 会话（TPM_SE_POLICY）
2. grub_tpm2_policy_pcr()           将当前 PCR 状态绑定到会话
3. grub_tpm2_unseal()               解封密钥（PCR不匹配则失败→密码提示）
4. grub_tpm2_flush_context()        清理 TPM 会话资源
```

---

## 二、文件变更清单

### 2.1 新建文件

#### TLCP 头文件（`include/grub/`）
| 文件 | 说明 |
|------|------|
| `include/grub/tlcp.h` | 公共 TLCP API 声明，含策略状态标志和错误码 |
| `include/grub/tlcp_sha256.h` | SHA256 上下文结构和接口声明 |
| `include/grub/tlcp_aes.h` | AES-128-CBC 接口声明 |
| `include/grub/efi/tlcp.h` | EFI TLCP 占位头文件 |

#### TPM2 头文件（`include/grub/efi/`，来自 grub2-2.02）
| 文件 | 说明 |
|------|------|
| `include/grub/tpm20.h` | TPM2 全量类型定义（TPML_*、TPMS_*、TPMU_* 等） |
| `include/grub/efi/tpm2tis.h` | TPM2 TIS 接口声明 |
| `include/grub/efi/tpm2session.h` | 会话管理接口声明 |
| `include/grub/efi/tpm2nvstorage.h` | NV 存储接口声明 |
| `include/grub/efi/tpm2getcapability.h` | 能力查询接口声明 |
| `include/grub/efi/tpm2object.h` | 密钥对象接口声明 |
| `include/grub/efi/tpm2context.h` | 上下文管理接口声明 |
| `include/grub/efi/tpm2startup.h` | TPM2 启动接口声明 |
| `include/grub/efi/tpm2enhancedauthorization.h` | PolicyPCR 等策略命令声明 |
| `include/grub/efi/tpm2integrity.h` | 完整性验证接口声明 |
| `include/grub/efi/tpm2/tpm2unmarshal_*.h` | 19 个 TPML/TPMS/TPMU 反序列化接口声明 |

#### TLCP 核心实现（`grub-core/kern/`）
| 文件 | 说明 |
|------|------|
| `grub-core/kern/tlcp.c` | 策略状态判断、完整性校验逻辑、密码提示循环、PCR 度量 |
| `grub-core/kern/tlcp_sha256.c` | SHA256 独立实现（freestanding 环境） |
| `grub-core/kern/tlcp_aes.c` | AES-128-CBC 独立实现（freestanding 环境） |

#### TLCP EFI 实现（`grub-core/kern/efi/`）
| 文件 | 说明 |
|------|------|
| `grub-core/kern/efi/tlcp.c` | TPM2 策略状态查询、状态文件读取、Unseal 操作 |

#### TPM2 命令库（`grub-core/kern/efi/`，来自 grub2-2.02）
| 文件 | 说明 |
|------|------|
| `tpm2tis.c` | TPM2 传输接口（通过 EFI submit_command） |
| `tpm2startup.c` | TPM2_Startup 命令 |
| `tpm2session.c` | TPM2_StartAuthSession 命令 |
| `tpm2nvstorage.c` | TPM2_NV_Read/Write 命令 |
| `tpm2getcapability.c` | TPM2_GetCapability 命令 |
| `tpm2object.c` | TPM2_Create/Load/Unseal 命令 |
| `tpm2context.c` | TPM2_FlushContext 命令 |
| `tpm2enhancedauthorization.c` | TPM2_PolicyPCR 等策略命令 |
| `tpm2integrity.c` | TPM2 完整性相关命令 |
| `tpm2_util/tpm2unmarshal_*.c` | 19 个 TPML/TPMS/TPMU 类型反序列化 |

### 2.2 修改文件

#### `grub-core/commands/boot.c`（Patch2001 中修改）
集成 TLCP 验证流程到 `grub_cmd_boot()` 函数：

```c
static grub_err_t
grub_cmd_boot (...)
{
    grub_measure_configured_files ();    /* 度量配置文件到 PCR 12 */

    if (grub_tpm_present ())
    {
        policy_state = grub_tpm_policy_state ();
        if (policy_state == POLICY_STATE_NONE)
            goto trust_end;
        else if (policy_state & POLICY_STATE_TPM_MASK)
        {
            if ((policy_state & POLICY_STATE_CHEKC_MASK) == POLICY_STATE_AUDIT)
                grub_tpm_integrity_validation (0);   /* 审计：不阻断 */
            else
                grub_tpm_integrity_validation (1);   /* 监督：失败则提示密码 */
        }
        else
            grub_file_integrity_validation (1);      /* 降级：必须输入密码 */
    }
    else
    {
        policy_state = grub_file_policy_state ();
        if (...SUPERVISORY...)
            grub_file_integrity_validation (1);
    }
trust_end:
    return grub_loader_boot ();
}
```

#### `grub-core/Makefile.core.def`（Patch2001 中修改）
在 `kernel = {}` 块内添加以下源文件（编译进 grubx64.efi 内核）：

```
# TLCP 核心（所有平台）
common = kern/tlcp.c;
common = kern/tlcp_sha256.c;
common = kern/tlcp_aes.c;

# TPM2 命令库（EFI 平台）
efi = kern/efi/tpm2tis.c;
efi = kern/efi/tpm2getcapability.c;
efi = kern/efi/tpm2startup.c;
efi = kern/efi/tpm2session.c;
efi = kern/efi/tpm2nvstorage.c;
efi = kern/efi/tpm2object.c;
efi = kern/efi/tpm2context.c;
efi = kern/efi/tpm2enhancedauthorization.c;
efi = kern/efi/tpm2integrity.c;
efi = kern/efi/tpm2_util/tpm2unmarshal_*.c;  # 19 个文件
efi = kern/efi/tlcp.c;
```

#### `grub-core/kern/efi/tpm2tis.c`（本次修改）
- 添加 `#define grub_efi_guid_t grub_guid_t` 兼容声明
- 原因：grub2-2.12 将 `grub_efi_guid_t` 重命名为 `grub_guid_t`

#### `grub-core/kern/efi/tpm2nvstorage.c`（本次修改）
- `GRUB_ERR_LOCKED` → `GRUB_ERR_IO`
- `GRUB_ERR_NOT_READY` → `GRUB_ERR_IO`
- 原因：这两个错误码在 grub2-2.12 的 `err.h` 中不存在

#### `grub-core/kern/tlcp_aes.c`（本次修改）
- 添加 `#include <grub/misc.h>` 和 `#define memcpy grub_memcpy`
- 原因：freestanding 构建环境中 `memcpy` 不可用

---

## 三、Patch 文件说明

### Patch2001：`0001-add-tlcp-trusted-boot-support.patch`

在 `grub.patches` 中位置：第 299 行

**内容**：
- 新增全部 TPM2 命令库文件（67 个文件，6923 行新增）
- 修改 `Makefile.core.def` 添加 TLCP 相关源文件条目
- 修改 `commands/boot.c` 集成 TLCP 验证调用
- 添加占位 TLCP 源文件（后被 Patch2003 替换）

### Patch2002：`0002-fix-tlcp-api-compat-grub2-2.12.patch`

在 `grub.patches` 中位置：第 300 行

**内容**（已被 Patch2003 覆盖，可考虑合并）：
- 修复 2.02→2.12 迁移中的 API 兼容性问题

### Patch2003：`0003-tlcp-rewrite-grub2-2.12-arch.patch`（本次生成）

**内容**：
- 完全重写 `kern/efi/tlcp.c`：基于 grub2-2.12 原生 TPM2 API
- 完全重写 `kern/tlcp.c`：使用 `grub_` 前缀函数名，清晰分层
- 完全重写 `include/grub/tlcp.h`：正确声明 grub2-2.12 函数签名
- 修复 `tpm2tis.c`、`tpm2nvstorage.c`、`tlcp_aes.c` 兼容性问题

---

## 四、grub.patches 修改说明

需要在 `/root/rpmbuild/SOURCES/grub.patches` 中添加 Patch2003：

```diff
 # TLCP trusted boot support
 Patch2001: 0001-add-tlcp-trusted-boot-support.patch
 Patch2002: 0002-fix-tlcp-api-compat-grub2-2.12.patch
+Patch2003: 0003-tlcp-rewrite-grub2-2.12-arch.patch
```

---

## 五、grub2.spec 修改说明（如需独立 spec patch）

grub2.spec 通过 `Source11: grub.patches` 统一管理所有 patch 文件。如果发行版采用独立 `%patch` 宏方式，需在 `%prep` 节添加：

```spec
# Source11: grub.patches 是补丁列表文件，由 %do_common_setup 自动处理
# 将 Patch2003 复制到 SOURCES 目录后，grub.patches 会自动引用
```

如需以独立 Patch 条目方式：

```spec
# grub2.spec %prep 节追加：
Patch2003: 0003-tlcp-rewrite-grub2-2.12-arch.patch
...
%prep
...
%patch2003 -p1
```

---

## 六、运行时文件依赖

GRUB2 运行时读取以下文件（由 tlcptool 部署时生成）：

| 文件 | 说明 |
|------|------|
| `/boot/policy.bin` | 策略状态（小端序 uint32：0=无 1=审计 2=监督） |
| `/boot/hardware_state.bin` | 硬件状态文件（SHA256(key) + AES加密载荷） |
| `/boot/software_state.bin` | 软件状态文件（同格式） |
| `/boot/host_st_configure.xml` | 度量配置文件，内容扩展到 PCR 12 |

TPM 持久存储：

| 句柄/索引 | 说明 |
|-----------|------|
| `0x81010101` | 硬件策略密钥（PCR 0,1,2,3,6,7 绑定） |
| `0x81010100` | 软件策略密钥（PCR 8,9,12 绑定） |
| `0x01800100` | 策略状态 NV 索引 |

---

## 七、状态文件格式

```
hardware_state.bin / software_state.bin 格式：
┌───────────────────────────────┐
│  SHA256(decryption_key) 32字节 │  ← 完整性校验
├───────────────────────────────┤
│  AES-128-CBC(magic, key) N字节 │  ← 解密后验证 magic 字符串
└───────────────────────────────┘

magic 字符串：
  硬件：INSPUR__HARDWARE
  软件：INSPUR__SOFTWARE

密钥格式（来自密码）：
  passphrase（hex string）→ 每2字符转1字节 → 128字节 key（零填充）
```

---

## 八、编译验证结果

使用 grub2-2.12 实际编译标志对所有文件进行语法检查：

```
编译标志：-std=gnu99 -ffreestanding -fshort-wchar -m64 -nostdinc
          -DGRUB_MACHINE_EFI=1 -DGRUB_MACHINE=X86_64_EFI
          -DGRUB_KERNEL=1 -DGRUB_FILE="..."
```

| 文件 | 结果 |
|------|------|
| kern/tlcp.c | OK |
| kern/efi/tlcp.c | OK |
| kern/tlcp_sha256.c | OK |
| kern/tlcp_aes.c | OK |
| kern/efi/tpm2tis.c | OK |
| kern/efi/tpm2startup.c | OK |
| kern/efi/tpm2session.c | OK |
| kern/efi/tpm2nvstorage.c | OK |
| kern/efi/tpm2getcapability.c | OK |
| kern/efi/tpm2object.c | OK |
| kern/efi/tpm2context.c | OK |
| kern/efi/tpm2enhancedauthorization.c | OK |
| kern/efi/tpm2integrity.c | OK |
| kern/efi/tpm2_util/（19个文件）| OK |
| **总计** | **32 个文件，0 错误** |

---

## 六、编译修复记录（rpmbuild -bb 实际编译阶段）

### Patch2004：tlcp.h 头文件独立性

**错误**：`include/grub/tlcp.h:62:1: error: unknown type name 'grub_err_t'`

**原因**：GRUB 构建系统用 `-DGRUB_SYMBOL_GENERATOR=1` 单独预处理 `KERNEL_HEADER_FILES`，此时没有预先包含 `grub/err.h`，导致 `grub_err_t` 未定义。

**修复**：在 `tlcp.h` 的 `#define GRUB_TLCP_HEADER 1` 后添加：
```c
#include <grub/err.h>
#include <grub/types.h>
```

### Patch2005：EXPORT_FUNC 符号导出

**错误**：`grub_file_integrity_validation in boot is not defined`

**原因**：GRUB `kernel_syms.lst` 由 `EXPORT_FUNC(name)` 模式从内核头文件提取。未加 `EXPORT_FUNC()` 的函数不被识别为内核符号，导致 moddep 报告 `boot` 模块引用了未定义符号。

**修复**：将 `tlcp.h` 中的 5 个公开内核 API 声明包装为 `EXPORT_FUNC(function_name)`：
```c
grub_err_t EXPORT_FUNC(grub_tpm_policy_state) (void);
grub_err_t EXPORT_FUNC(grub_file_policy_state) (void);
// ...等
```

### Patch2006：移除 efi_call_X 宏

**错误**：`grub-mkimage: error: undefined symbol efi_call_5`

**原因**：`tpm2tis.c` 使用了 `efi_call_2()` / `efi_call_5()` 宏（grub2-2.02 风格），这些宏在 grub2-2.12 已被移除。

**修复**：直接调用 EFI 协议方法（`__grub_efi_api` 属性处理调用约定）：
```c
// 2.02: status = efi_call_2(tpm->get_capability, tpm, &caps);
// 2.12:
status = tpm->get_capability(tpm, &caps);
```

### Patch2007：避免依赖 tpm 模块的 grub_tpm_measure

**错误**：`grub-mkimage: error: undefined symbol grub_tpm_measure`

**原因**：`grub_tpm_measure()` 定义在 `tpm` 模块（`commands/efi/tpm.c`），不在内核。`kern/tlcp.c`（内核）直接调用该模块函数导致链接错误。

**修复**：在 `kern/efi/tlcp.c` 添加 `grub_tlcp_efi_measure()` 函数，直接使用 `EFI_TCG2_PROTOCOL.hash_log_extend_event()`，`kern/tlcp.c` 通过 `#if defined(GRUB_MACHINE_EFI)` 守卫调用它。

### Patch2008：grub_tpm_present 平台守卫

**错误**：`grub_tpm_present in boot is not defined`（i386-pc 构建）

**原因**：`grub_tpm_present()` 只在 EFI 和 powerpc_ieee1275 的 `tpm` 模块中定义，i386-pc 没有该函数。

**修复**：在 `commands/boot.c` 中用平台宏保护该调用：
```c
#if defined(GRUB_MACHINE_EFI) || defined(GRUB_MACHINE_IEEE1275)
  if (grub_tpm_present())
    { ... }
  else
#endif
  { /* file-based policy fallback */ }
```

---

## 七、最终补丁列表

| 补丁 | 文件名 | 说明 |
|------|--------|------|
| Patch2001 | 0001-add-tlcp-trusted-boot-support.patch | Makefile + boot.c 集成框架 |
| Patch2002 | 0002-fix-tlcp-api-compat-grub2-2.12.patch | API 兼容（grub_guid_t 等）|
| Patch2003 | 0003-tlcp-rewrite-grub2-2.12-arch.patch | 全部 TLCP 实现文件 |
| Patch2004 | 0004-tlcp-fix-header-self-contained.patch | tlcp.h 头文件独立性 |
| Patch2005 | 0005-tlcp-export-kernel-symbols-EXPORT-FUNC.patch | EXPORT_FUNC 内核符号导出 |
| Patch2006 | 0006-tlcp-replace-efi-call-macros-direct-calls.patch | 移除 efi_call_X 宏 |
| Patch2007 | 0007-tlcp-avoid-grub-tpm-measure-use-efi-tcg2-direct.patch | 直接使用 EFI TCG2 协议 |
| Patch2008 | 0008-tlcp-guard-grub-tpm-present-platform.patch | grub_tpm_present 平台守卫 |

**构建输出**：`/root/rpmbuild/RPMS/x86_64/grub2-efi-x64-2.12-22.an23.x86_64.rpm`（及其他 17 个 RPM 包）

**SRPM**：`/root/rpmbuild/SRPMS/grub2-2.12-22.an23.src.rpm`
