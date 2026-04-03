# GRUB2 可信启动检测（TLCP）迁移方案
## 从 grub2-2.02 迁移到 grub2-2.12

**版本**：1.0  
**日期**：2026-04-02  
**状态**：架构评估完成  
**适用对象**：系统架构师、GRUB2 维护者

---

## 第一部分：grub2-2.12 架构概述

### 1.1 版本对比总结

| 维度 | grub2-2.02 | grub2-2.12 | 迁移影响 |
|------|-----------|-----------|--------|
| **Boot 命令** | 简单直接，无 preboot hook | 完整的 preboot hook 框架 | **无需改造** boot 命令本身；通过 hook 注册实现 TLCP 检查 |
| **TPM 支持** | 无内置 TPM2 库 | 原生 TPM/TPM2 命令模块 + EFI 协议封装 | 可复用现有 TPM2 EFI 接口；减少自定义代码 |
| **Makefile 语法** | kernel/module 定义语法同 2.12 | 一致 | **语法无变化**；直接复用声明方式 |
| **EFI TPM 头文件** | `include/grub/efi/tpm.h`（基础） | `include/grub/efi/tpm.h`（完整 TPM2 结构） | 2.12 已定义 `grub_efi_tpm2_protocol_t`；2.02 自定义接口需适配 |
| **Preboot Hook 机制** | 无 | 完整框架（优先级链表） | **建议使用** preboot hook 替代在 boot 中硬编码 TLCP 逻辑 |

### 1.2 关键新增架构（grub2-2.12）

#### A. Preboot Hook 系统

**源文件**：`/root/rpmbuild/BUILD/grub-2.12/grub-core/commands/boot.c`，行 44-126

GRUB2-2.12 引入了**优先级链表式 preboot hook** 机制，允许多个模块注册启动前的钩子函数：

```c
struct grub_preboot {
  grub_err_t (*preboot_func) (int flags);         // 启动前执行
  grub_err_t (*preboot_rest_func) (void);         // 启动后恢复
  grub_loader_preboot_hook_prio_t prio;           // 优先级
  struct grub_preboot *next, *prev;               // 链表指针
};
```

**执行流程** (`grub_loader_boot()` 函数，行 190-220)：
1. 检查是否加载了内核
2. 调用 `grub_machine_fini()`（停用机器驱动）
3. **按优先级顺序**执行所有 preboot hook 的 `preboot_func()`
4. 执行实际的 boot loader 函数
5. **反序**执行所有 hook 的 `preboot_rest_func()`（清理）

**API 接口**（行 87-126）：
- `grub_loader_register_preboot_hook()` — 注册 hook
- `grub_loader_unregister_preboot_hook()` — 注销 hook

**迁移建议**：
> TLCP 验证应通过注册一个 **preboot hook** 实现，而非直接修改 `grub_cmd_boot()` 函数。这样可保持引导流程解耦、易于维护。

---

#### B. EFI TPM2 协议支持

**源文件**：`/root/rpmbuild/BUILD/grub-2.12/include/grub/efi/tpm.h`，行 152-193

GRUB2-2.12 原生定义了 TPM2 EFI 协议结构体，支持以下方法：

```c
struct grub_efi_tpm2_protocol {
  // 获取 TPM 能力（支持的哈希算法、PCR 数量等）
  grub_efi_status_t (*get_capability)(...)
  
  // 获取 TPM 事件日志
  grub_efi_status_t (*get_event_log)(...)
  
  // 哈希、日志、扩展 PCR（三合一）
  grub_efi_status_t (*hash_log_extend_event)(...)
  
  // 向 TPM 发送原始命令
  grub_efi_status_t (*submit_command)(...)
  
  // 获取/设置活跃的 PCR 哈希算法银行
  grub_efi_status_t (*get_active_pcr_banks)(...)
  grub_efi_status_t (*set_active_pcr_banks)(...)
  
  // 检查异步 PCR 银行设置操作的结果
  grub_efi_status_t (*get_result_of_set_active_pcr_banks)(...)
};
```

**现状**（grub2-2.02）：
- 需要自定义 TPM2 命令包装库（约 23 个 `.c` 文件）
- 包括 TPM2 startup、session、policy、unseal、nvstorage 等底层命令

**迁移路径**：
1. **复用内置接口**：通过 `grub_efi_locate_handle()` 获取 TPM2 protocol 实例
2. **调用 EFI TPM2 API**：使用 `hash_log_extend_event()` 进行度量
3. **简化自定义代码**：只需实现 TLCP 策略层，不需 23 个 TPM2 命令库文件

---

### 1.3 TPM 命令模块分析

**源文件**：`/root/rpmbuild/BUILD/grub-2.12/grub-core/commands/tpm.c`（EFI 部分在 `commands/efi/tpm.c`）

#### TPM 度量框架

grub2-2.12 提供了基础的 TPM 度量接口：

```c
// grub/tpm.h 中定义
grub_err_t grub_tpm_measure(unsigned char *buf, 
                            grub_size_t size,
                            grub_uint8_t pcr,
                            const char *description);
int grub_tpm_present(void);
```

#### TPM 文件验证器

grub2-2.12 通过**文件验证器**（verifier）框架集成 TPM 度量：
- 自动度量加载的文件内容到 PCR-9
- 度量内核命令行到 PCR-8
- 按类型标记事件（kernel_cmdline, module_cmdline, grub_cmd）

**迁移建议**：
> TLCP 的**完整性校验**应通过与此框架集成，而非独立的读取和验证。这样可共享 TPM 设备句柄、统一错误处理。

---

### 1.4 Makefile 内核构建语法

**源文件**：`/root/rpmbuild/BUILD/grub-2.12/grub-core/Makefile.core.def`，行 47-300

GRUB2-2.12 的 kernel 块定义保持与 2.02 一致：

```makefile
kernel = {
  name = kernel;
  
  # 平台特定编译标志
  x86_64_efi_cflags = '-fshort-wchar';
  x86_64_efi_ldflags = '-Wl,-r';
  
  # 源文件声明
  common = kern/buffer.c;
  common = kern/command.c;
  efi = kern/efi/efi.c;
  efi = kern/efi/mm.c;
  # ...
};
```

**TPM 模块声明**（行 2628-2630）：

```makefile
module = {
  name = tpm;
  common = commands/tpm.c;
  efi = commands/efi/tpm.c;
  enable = efi;
};
```

**迁移建议**：
> TLCP 可作为一个新 **kernel 构建块**（而非 module），声明方式示例如下（见第四部分）。

---

## 第二部分：迁移可行性评估

### 2.1 可直接复用的文件（无改造）

| 源文件（grub2-2.02） | 状态 | 说明 |
|-----------------|------|------|
| `grub-core/kern/tlcp_sha256.c` | ✅ 直接复用 | SHA256 纯 C 实现，无平台依赖 |
| `grub-core/kern/tlcp_aes.c` | ✅ 直接复用 | AES-128-CBC 实现，无平台依赖 |
| `include/grub/tlcp_sha256.h` | ✅ 直接复用 | 头文件声明 |
| `include/grub/tlcp_aes.h` | ✅ 直接复用 | 头文件声明 |

**文件数量**：4 个文件，约 650 行代码
**风险等级**：绿色（低）

---

### 2.2 需要轻度改造的文件

#### A. `grub-core/kern/tlcp.c`（~1116 行）

**改造点**：

| 行号范围 | 内容 | 改造方式 |
|---------|------|---------|
| 1-50 | 头文件包含 | 去除 grub2-2.02 自定义 TPM2 库头文件，改为 `#include <grub/efi/tpm.h>` |
| 100-200 | `measure_configured_files()` | 调用改为 `grub_tpm_measure()` 替代自定义 TPM2 度量接口 |
| 250-450 | `tpm_policy_state()` | 修改为调用 grub2-2.12 的 EFI TPM2 protocol 的 `submit_command()` |
| 500-700 | `tpm_integrity_validation()` | 改造为 preboot hook 函数签名：`grub_err_t tlcp_preboot(int flags)` + `grub_err_t tlcp_preboot_rest(void)` |
| 800-1000 | 密码验证逻辑 | 保留 AES-CBC 解密和密钥标识串检查 |

**改造难度**：中等（30% 代码重写）

---

#### B. `grub-core/kern/efi/tlcp.c`（~819 行）

**现状**：grub2-2.02 中自定义的 EFI TPM2 协议封装

**改造策略**：**部分替代**

| 功能块 | 行号 | 处理方式 |
|------|------|---------|
| TPM2 handle 查找 | ~100-150 | 使用 grub2-2.12 内置的 `grub_efi_locate_handle()` |
| session 创建 | ~200-300 | 复用或改为直接调用 EFI protocol 的 `submit_command()` |
| policy 计算 | ~400-600 | 保留 HMAC 计算逻辑，改为调用 grub2-2.12 crypto 库（如有） |
| unseal 操作 | ~700-819 | 改为调用 EFI TPM2 protocol 的 `submit_command()` 发送标准 TPM2_Unseal 命令 |

**改造难度**：中等-高（50% 代码重写）

---

#### C. `grub-core/commands/boot.c`（6 行代码插入点）

**现状**（grub2-2.02）：
```c
static grub_err_t
grub_cmd_boot(struct grub_command *cmd __attribute__ ((unused)),
              int argc __attribute__ ((unused)),
              char *argv[] __attribute__ ((unused)))
{
  /* TLCP 验证插入点 */
  grub_err_t err = grub_tlcp_boot_check();
  if (err != GRUB_ERR_NONE) return err;
  
  return grub_loader_boot();
}
```

**改造方式**：**完全替换为 preboot hook 注册**

grub2-2.12 中 `boot.c` 无需改造，只需在 TLCP 模块的 `GRUB_MOD_INIT()` 中注册 hook：

```c
GRUB_MOD_INIT(tlcp)
{
  tlcp_preboot_hook = grub_loader_register_preboot_hook(
    tlcp_preboot,           // preboot_func
    tlcp_preboot_rest,      // preboot_rest_func
    GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL
  );
}
```

**改造难度**：低（无需修改 boot.c）

---

### 2.3 需要移除的文件（grub2-2.02 自定义实现）

以下文件在 grub2-2.12 中已由内置模块替代，**不应复用**：

| 文件 | 行数 | 原因 |
|------|------|------|
| `grub-core/kern/efi/tpm2_startup.c` | ~100 | grub2-2.12 EFI 直接支持 TPM2 |
| `grub-core/kern/efi/tpm2_session.c` | ~150 | 改为使用 EFI TPM2 protocol |
| `grub-core/kern/efi/tpm2_policy.c` | ~200 | 改为使用 EFI TPM2 protocol |
| `grub-core/kern/efi/tpm2_unseal.c` | ~150 | 改为使用 EFI TPM2 protocol |
| `grub-core/kern/efi/tpm2_nvstorage.c` | ~120 | 改为使用 EFI TPM2 protocol |
| 其他 `tpm2_*.c` 文件（共 ~18 个） | ~1500 | 统一用 EFI TPM2 protocol 替代 |

**总计移除**：约 2000 行代码（简化！）

---

### 2.4 改造文件汇总

| 类别 | 文件 | 改造量 | 风险 |
|------|------|--------|------|
| **直接复用** | tlcp_sha256.c/h, tlcp_aes.c/h | 0% | 绿色 ✅ |
| **轻度改造** | tlcp.c | 30% | 绿色-黄 ⚠️ |
| **中度改造** | efi/tlcp.c | 50% | 黄 ⚠️ |
| **设计改造** | 无需修改 boot.c；通过 preboot hook | - | 绿色 ✅ |
| **移除** | 23 个 tpm2_*.c 库文件 | 替代 | 绿色 ✅ |

---

## 第三部分：详细适配清单

### 3.1 头文件适配

#### 新增头文件声明

**文件**：`include/grub/tlcp.h`

```c
#ifndef GRUB_TLCP_HEADER
#define GRUB_TLCP_HEADER 1

#include <grub/err.h>
#include <grub/efi/tpm.h>
#include <grub/efi/efi.h>

/* TLCP 策略状态 */
#define TLCP_POLICY_AUDIT 1
#define TLCP_POLICY_SUPERVISORY 2

/* Preboot hook 函数签名 */
grub_err_t grub_tlcp_preboot(int flags);
grub_err_t grub_tlcp_preboot_rest(void);

/* 核心 TLCP 函数 */
grub_err_t grub_tlcp_measure_files(void);
grub_err_t grub_tlcp_integrity_check(int halt_on_fail);

#endif
```

**修改原因**：
- 行 1-20：声明 preboot hook 函数接口
- 行 21-30：保留密码验证接口（使用 AES-CBC）

---

#### 修改 `include/grub/efi/tlcp.h`

**改造点**：
- 去除 grub2-2.02 中的自定义 TPM2 command 结构体
- 改为使用 `grub_efi_tpm2_protocol_t`（来自 grub/efi/tpm.h）

**新增内容**：
```c
#include <grub/efi/tpm.h>

/* EFI TPM2 protocol 提供的接口已足够 */
typedef struct grub_efi_tpm2_protocol grub_efi_tpm2_protocol_t;

grub_err_t grub_tlcp_efi_get_tpm2_protocol(
  grub_efi_tpm2_protocol_t **tpm2_protocol);
grub_err_t grub_tlcp_efi_unseal(
  grub_efi_tpm2_protocol_t *tpm2_protocol,
  ...);
```

---

### 3.2 核心实现文件改造

#### `grub-core/kern/tlcp.c` — 主 TLCP 逻辑

**关键改造（伪代码）**：

**原 2.02 风格**：
```c
// grub2-2.02
static grub_err_t
measure_configured_files(void)
{
  /* 调用自定义 TPM2 library */
  tpm2_startup_clear();
  tpm2_create_session();
  tpm2_policy_pcr(...);
  
  for (each file in config) {
    tpm2_pcrextend(file_hash);
  }
}
```

**改造后（2.12 风格）**：
```c
// grub2-2.12
static grub_err_t
tlcp_measure_configured_files(void)
{
  grub_err_t status;
  unsigned char file_hash[GRUB_SHA256_DIGEST_SIZE];
  
  /* 使用 grub2-2.12 原生 TPM 度量接口 */
  for (each file in config) {
    // 计算文件 SHA256
    status = grub_tlcp_sha256_file(file_path, file_hash);
    if (status != GRUB_ERR_NONE) return status;
    
    // 度量到 PCR（通过 TPM verifier framework）
    status = grub_tpm_measure(file_hash,
                             GRUB_SHA256_DIGEST_SIZE,
                             8,  // GRUB_STRING_PCR
                             file_path);
    if (status != GRUB_ERR_NONE) return status;
  }
  
  return GRUB_ERR_NONE;
}
```

**改造点列表**：

| 行号 | 原函数名 | 改造为 | 说明 |
|------|---------|--------|------|
| ~50 | - | `grub_tlcp_sha256_file()` | 新增：读文件并计算 SHA256 |
| ~100-200 | `measure_configured_files()` | `tlcp_measure_configured_files()` | 改为使用 `grub_tpm_measure()` |
| ~250-450 | `tpm_policy_state()` | `tlcp_get_policy_state()` | 改为通过 EFI TPM2 protocol 查询 NV |
| ~500-700 | `tpm_integrity_validation()` | `tlcp_preboot()` | **关键改造**：改为 preboot hook 函数 |
| ~800-1000 | `file_integrity_validation()` | `tlcp_validate_password()` | 保留 AES-CBC 密码验证逻辑 |

---

#### `grub-core/kern/efi/tlcp.c` — EFI TPM2 操作

**关键改造（仅保留必要函数）**：

| 原函数 | 行号 | 改造方式 |
|-------|------|---------|
| `tpm2_get_handle()` | ~50-150 | 改为调用 `grub_efi_locate_handle()` |
| `tpm2_create_session()` | ~200-250 | **保留**但改为直接调用 EFI protocol |
| `tpm2_policy_pcr()` | ~300-400 | **可选**：若 EFI TPM2 不支持 policy，则保留；否则移除 |
| `tpm2_unseal()` | ~700-819 | **改造**：改为调用 EFI TPM2 `submit_command()` 或配置使用 TSS2 库 |

**新增接口**：
```c
grub_err_t
grub_tlcp_efi_get_tpm2(grub_efi_tpm2_protocol_t **tpm2)
{
  grub_efi_handle_t *handles;
  grub_efi_uintn_t num;
  
  /* 获取 TPM2 protocol 实例 */
  handles = grub_efi_locate_handle(GRUB_EFI_BY_PROTOCOL,
                                    &tpm2_guid, NULL, &num);
  if (!handles || num == 0)
    return grub_error(GRUB_ERR_UNKNOWN_DEVICE, "TPM2 not found");
  
  *tpm2 = (grub_efi_tpm2_protocol_t*) 
    grub_efi_open_protocol(handles[0], &tpm2_guid, ...);
  
  return GRUB_ERR_NONE;
}
```

---

### 3.3 新增模块入口文件

#### `grub-core/kern/tlcp_module.c` — TLCP 模块初始化

```c
#include <grub/dl.h>
#include <grub/err.h>
#include <grub/loader.h>
#include <grub/tlcp.h>

GRUB_MOD_LICENSE("GPLv3+");

static struct grub_preboot *tlcp_preboot_handle = NULL;

/* Preboot hook 函数 */
static grub_err_t
tlcp_preboot(int flags __attribute__((unused)))
{
  grub_dprintf("tlcp", "TLCP boot check started\n");
  
  /* 1. 检查策略状态 */
  enum policy_state state = tlcp_get_policy_state();
  if (state == POLICY_NOT_EXIST) {
    grub_dprintf("tlcp", "No TLCP policy deployed\n");
    return GRUB_ERR_NONE;  // 无政策，允许启动
  }
  
  /* 2. 度量配置文件 */
  grub_err_t err = tlcp_measure_configured_files();
  if (err != GRUB_ERR_NONE) {
    grub_dprintf("tlcp", "File measurement failed: %d\n", err);
    return err;
  }
  
  /* 3. 完整性验证 */
  if (state == POLICY_SUPERVISORY) {
    err = tlcp_integrity_validation(1);  // halt_on_fail = 1
    if (err != GRUB_ERR_NONE) {
      grub_error(GRUB_ERR_ACCESS_DENIED, 
                 "TLCP integrity check failed");
      return err;
    }
  }
  
  grub_dprintf("tlcp", "TLCP boot check passed\n");
  return GRUB_ERR_NONE;
}

static grub_err_t
tlcp_preboot_rest(void)
{
  grub_dprintf("tlcp", "TLCP boot check finished\n");
  return GRUB_ERR_NONE;
}

GRUB_MOD_INIT(tlcp)
{
  grub_dprintf("tlcp", "TLCP module initializing\n");
  
  /* 注册 preboot hook */
  tlcp_preboot_handle = grub_loader_register_preboot_hook(
    tlcp_preboot,
    tlcp_preboot_rest,
    GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL
  );
  
  if (!tlcp_preboot_handle)
    grub_error(GRUB_ERR_OUT_OF_MEMORY, 
               "Failed to register TLCP preboot hook");
}

GRUB_MOD_FINI(tlcp)
{
  if (tlcp_preboot_handle)
    grub_loader_unregister_preboot_hook(tlcp_preboot_handle);
}
```

---

## 第四部分：Makefile.core.def 集成方案

### 4.1 TLCP 作为 kernel 构建块

**位置**：`/root/rpmbuild/BUILD/grub-2.12/grub-core/Makefile.core.def`

**插入点**：在 EFI 相关源文件声明之后（约行 225），添加：

```makefile
  # TLCP 可信启动检测（仅 EFI）
  efi = kern/tlcp.c;
  efi = kern/efi/tlcp.c;
  efi = kern/tlcp_sha256.c;
  efi = kern/tlcp_aes.c;
  efi = kern/tlcp_module.c;
```

**说明**：
- `efi =` 前缀表示此文件仅在 EFI 构建中包含
- 其他平台（PC、coreboot）可选：若无 EFI TPM，则不编译

---

### 4.2 TLCP 头文件路径

确保以下头文件在 include 搜索路径中：

```makefile
# 在 grub-core/Makefile.core.def 顶部（如有）或 configure.ac 中添加
CPPFLAGS += -I$(srcdir)/include/grub/efi
```

---

### 4.3 完整 Makefile 片段示例

```makefile
# ============ 原有 EFI 支持 ============
  efi = disk/efi/efidisk.c;
  efi = kern/efi/efi.c;
  efi = kern/efi/debug.c;
  efi = kern/efi/init.c;
  efi = kern/efi/mm.c;
  efi = term/efi/console.c;
  efi = kern/acpi.c;
  efi = kern/efi/acpi.c;
  efi = kern/efi/sb.c;
  efi = kern/lockdown.c;
  efi = lib/envblk.c;

# ============ 新增：TLCP 可信启动检测 ============
  # 核心 TLCP 逻辑
  efi = kern/tlcp.c;
  efi = kern/efi/tlcp.c;
  
  # 密码学库（SHA256, AES）
  efi = kern/tlcp_sha256.c;
  efi = kern/tlcp_aes.c;
  
  # TLCP 模块入口（preboot hook 注册）
  efi = kern/tlcp_module.c;
```

---

## 第五部分：boot.c 修改方案

### 5.1 关键结论

**grub2-2.12 中的 boot.c 无需修改！**

**原因**：
1. TLCP 检查通过 **preboot hook 机制**在 `grub_loader_boot()` 中自动执行
2. `grub_cmd_boot()` 函数保持原样（行 224-228）
3. TLCP 模块的 `GRUB_MOD_INIT()` 注册 hook，启动时自动触发

**流程示意**：
```
boot 命令执行
  → grub_cmd_boot()
    → grub_loader_boot()
      → [自动执行所有 preboot hook]
         → tlcp_preboot() ✅ TLCP 检查在此执行
         → [其他 hook...]
      → 实际 boot loader（kernel 跳转）
```

---

### 5.2 若 grub2-2.02 直接修改了 boot.c

如果 grub2-2.02 修改了 boot.c（例如在 `grub_cmd_boot()` 中硬编码调用）：

**原 grub2-2.02 修改示例**：
```c
static grub_err_t
grub_cmd_boot(struct grub_command *cmd __attribute__ ((unused)),
              int argc __attribute__ ((unused)),
              char *argv[] __attribute__ ((unused)))
{
  grub_err_t err = grub_tlcp_boot_check();  // ← 硬编码
  if (err != GRUB_ERR_NONE)
    return err;
  
  return grub_loader_boot();
}
```

**改造方式**：
1. **删除** TLCP 检查的硬编码调用
2. 恢复为原始版本
3. 让 TLCP 模块通过 preboot hook 注册

**git diff 表示**：
```diff
--- a/grub-core/commands/boot.c
+++ b/grub-core/commands/boot.c
@@ -224,9 +224,6 @@ grub_cmd_boot (struct grub_command *cmd __attribute__ ((unused)),
-  grub_err_t err = grub_tlcp_boot_check();
-  if (err != GRUB_ERR_NONE)
-    return err;
-
   return grub_loader_boot();
 }
```

---

## 第六部分：潜在冲突点分析

### 6.1 TPM 设备句柄冲突

**问题**：grub2-2.12 的 TPM 命令模块（`commands/tpm.c`）和 TLCP 都需要访问 TPM2 设备。

**现状**：
- `grub-core/commands/tpm.c` 行 37-38：定义全局 `grub_tpm_handle` 和 `grub_tpm_version`
- TLCP 若独立查询 TPM2 handle，可能获得不同的句柄或版本不一致

**解决方案**：
1. **复用全局句柄**：TLCP 中调用 `grub_tpm_measure()` 而非直接操作 EFI protocol
2. **单点初始化**：在 `grub_loader_boot()` 之前，统一初始化 TPM2 context
3. **头文件共享**：在 `include/grub/tpm.h` 中导出 TPM 版本查询接口

**推荐实现**：
```c
// include/grub/tpm.h 中新增
int grub_tpm_get_version(void);
grub_efi_tpm2_protocol_t* grub_tpm_get_protocol(void);
```

---

### 6.2 预启动钩子优先级冲突

**问题**：若多个模块注册 preboot hook，执行顺序可能影响结果。

**现状**：
- grub2-2.12 通过优先级链表管理（`grub_loader_preboot_hook_prio_t`）
- TLCP 需要在其他验证（如 SecureBoot）之后执行

**解决方案**：
```c
/* TLCP preboot hook 优先级选择 */
tlcp_preboot_handle = grub_loader_register_preboot_hook(
  tlcp_preboot,
  tlcp_preboot_rest,
  GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL  // 或 PRIO_LOW
);
```

**建议**：
- TLCP 应为 `GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL`（标准）
- 如需保证后执行，改为 `PRIO_LOW`（需要 grub2-2.12 定义此常量）

---

### 6.3 EFI 协议查询冲突

**问题**：TPM2 protocol 查询可能在 EFI 初始化未完成时失败。

**现状**：
- `grub_loader_boot()` 调用 `grub_machine_fini()`（行 199），关闭机器驱动
- 之后 preboot hook 执行（行 201-210）
- EFI 设备可能已不可用

**解决方案**：
1. **提前查询**：在 TLCP 模块初始化时缓存 TPM2 protocol 指针
2. **延迟操作**：不在 hook 中查询设备，仅执行预缓存的命令

**改造代码**：
```c
GRUB_MOD_INIT(tlcp)
{
  /* 预缓存 TPM2 protocol */
  grub_tlcp_efi_get_tpm2_protocol(&cached_tpm2_protocol);
  
  tlcp_preboot_handle = grub_loader_register_preboot_hook(
    tlcp_preboot,
    tlcp_preboot_rest,
    GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL
  );
}
```

---

### 6.4 密码学库选择

**问题**：grub2-2.12 已有加密库（libgcrypt），TLCP 自带的 SHA256/AES 可能重复。

**现状**（grub2-2.12）：
- `grub-core/lib/crypto.c`：提供通用密码学接口
- `grub-core/lib/libgcrypt*`：集成的 libgcrypt 库（RSA、AES 等）

**冲突分析**：
- TLCP 的 `tlcp_sha256.c`：简单的纯 C SHA256，无依赖
- TLCP 的 `tlcp_aes.c`：简单的纯 C AES-128-CBC，无依赖
- grub2-2.12 的 libgcrypt：功能完整但可能增加空间开销

**建议方案**：
1. **保留 TLCP 自带**：SHA256 和 AES-128-CBC 的纯 C 实现
2. **理由**：
   - TLCP 代码独立性强
   - EFI 环境下空间受限，自带库足够轻量
   - 无需额外依赖 libgcrypt

---

## 第七部分：推荐 Patch 文件列表

### 7.1 分阶段构建方案

建议将 TLCP 迁移拆分为 **5 个独立的 patch**，便于审查和测试：

#### Patch 1: 基础头文件和密码库
**文件**：`0001-tlcp-add-header-files-and-crypto-libs.patch`
```
新增文件：
  - include/grub/tlcp.h
  - include/grub/tlcp_sha256.h
  - include/grub/tlcp_aes.h
  - include/grub/efi/tlcp.h
  - grub-core/kern/tlcp_sha256.c
  - grub-core/kern/tlcp_aes.c

无改动文件
```
**审查重点**：密码学库的正确性（与 grub2-2.02 无差异）

---

#### Patch 2: EFI TPM2 操作层
**文件**：`0002-tlcp-efi-tpm2-operations.patch`
```
新增文件：
  - grub-core/kern/efi/tlcp.c

改动：
  - include/grub/efi/tlcp.h
```
**审查重点**：
- EFI protocol 调用的正确性
- NV 读写逻辑
- Unseal 命令的构造

---

#### Patch 3: TLCP 核心逻辑
**文件**：`0003-tlcp-core-policy-logic.patch`
```
新增文件：
  - grub-core/kern/tlcp.c

改动：
  - include/grub/tlcp.h
```
**审查重点**：
- 度量逻辑与 grub2-2.02 的功能等价性
- 错误处理和日志输出
- AES 密码验证逻辑

---

#### Patch 4: TLCP 模块入口（Preboot Hook）
**文件**：`0004-tlcp-preboot-hook-module.patch`
```
新增文件：
  - grub-core/kern/tlcp_module.c

改动：
  - include/grub/tlcp.h
```
**审查重点**：
- preboot hook 函数签名
- hook 注册/注销逻辑
- 与 boot.c 的集成方式

---

#### Patch 5: Makefile 集成
**文件**：`0005-tlcp-makefile-integration.patch`
```
改动：
  - grub-core/Makefile.core.def（kernel 块中添加 TLCP 源文件）
```
**审查重点**：
- 文件路径正确性
- EFI 平台限制（`efi =` 前缀）
- 构建依赖关系

---

### 7.2 逐个验证清单

```bash
# 验证 Patch 1：密码库
make clean && make
# 测试：grub-mkimage -o test.efi -O x86_64-efi ...

# 验证 Patch 2：EFI TPM2
# 功能测试：在 EFI 环境下查询 TPM2 protocol

# 验证 Patch 3：TLCP 核心
# 单元测试：测试度量、策略检查、密码验证函数

# 验证 Patch 4：Preboot Hook
# 集成测试：启动流程中验证 hook 是否被调用

# 验证 Patch 5：Makefile
# 构建测试：确保 TLCP 文件被编译到内核
```

---

## 第八部分：风险评估与缓解

### 8.1 高风险项

| 风险 | 等级 | 缓解措施 |
|------|------|--------|
| EFI TPM2 protocol 在 preboot 阶段不可用 | 🔴 高 | 预缓存 protocol 指针；提前测试 EFI 初始化顺序 |
| TPM 度量失败导致启动中断 | 🔴 高 | 实现 fail-open 模式：策略检查失败时仅警告，不阻断 |
| NV 存储空间不足 | 🟡 中 | 检查 NV 剩余空间；优化存储格式 |

### 8.2 中风险项

| 风险 | 等级 | 缓解措施 |
|------|------|--------|
| grub2-2.12 版本变更（2.13 等）导致接口不兼容 | 🟡 中 | 版本检查；抽象接口层 |
| TLCP 与其他 preboot hook 的交互 | 🟡 中 | 明确优先级；充分集成测试 |

### 8.3 验证测试计划

```
单元测试：
  - SHA256/AES 单元测试（复用 grub2-2.02 的测试用例）
  - EFI TPM2 接口测试（mock TPM2 protocol）
  
集成测试：
  - 完整启动流程测试（启用 TLCP，验证 preboot hook 执行）
  - TPM 策略应用测试（导入策略，验证检查逻辑）
  - 密码验证测试（硬/软密码输入验证）
  
平台测试：
  - UEFI x86_64 EFI（主要平台）
  - UEFI ARM64 EFI（备选平台）
```

---

## 第九部分：文件清单

### 9.1 待新增文件（grub2-2.12）

```
grub-core/
├── kern/
│   ├── tlcp.c                    # 核心策略逻辑（改造自 2.02）
│   ├── tlcp_module.c             # 模块入口 + preboot hook（新增）
│   ├── tlcp_sha256.c             # SHA256（直接复用）
│   ├── tlcp_aes.c                # AES-128-CBC（直接复用）
│   └── efi/
│       └── tlcp.c                # EFI TPM2 操作（改造自 2.02）
│
└── include/grub/
    ├── tlcp.h                    # TLCP 公开 API（新增/改造）
    ├── tlcp_sha256.h             # SHA256 头文件（直接复用）
    ├── tlcp_aes.h                # AES 头文件（直接复用）
    └── efi/
        └── tlcp.h                # EFI TLCP 接口（改造自 2.02）
```

### 9.2 待改动文件（grub2-2.12）

```
grub-core/
└── Makefile.core.def             # 行 225 之后：添加 TLCP kernel 源文件声明
```

### 9.3 不动文件（grub2-2.12）

```
grub-core/commands/boot.c         # 无需修改！使用 preboot hook
```

---

## 第十部分：总结与建议

### 10.1 迁移步骤（执行顺序）

1. **阶段 1**：准备（2-3 天）
   - 在 grub2-2.12 源码树中创建分支
   - 复制密码库文件（tlcp_sha256.c/h, tlcp_aes.c/h）
   - 编译测试

2. **阶段 2**：EFI 层改造（1 周）
   - 改写 efi/tlcp.c，改为调用 EFI TPM2 protocol
   - 测试 TPM2 设备通信

3. **阶段 3**：核心逻辑改造（1 周）
   - 改写 tlcp.c，集成度量和策略逻辑
   - 改为 preboot hook 函数签名
   - 单元测试

4. **阶段 4**：模块入口和集成（3-5 天）
   - 编写 tlcp_module.c
   - 修改 Makefile.core.def
   - 构建测试

5. **阶段 5**：系统集成测试（1 周）
   - 完整 EFI 启动测试
   - TPM 策略部署和验证
   - 密码输入和验证

### 10.2 关键建议

✅ **推荐**：
- 使用 preboot hook 机制替代硬编码
- 复用 grub2-2.12 的 EFI TPM2 protocol，减少自定义代码
- 保留 SHA256/AES 纯 C 实现（轻量、独立）
- 分 5 个 patch 逐步合并，便于审查

⚠️ **需注意**：
- EFI 初始化顺序对 TPM2 可用性的影响
- preboot hook 与其他模块的优先级冲突
- TPM 设备句柄的全局管理

❌ **避免**：
- 复用 grub2-2.02 的 23 个 tpm2_*.c 库文件（已由 grub2-2.12 内置 EFI TPM2 替代）
- 直接修改 boot.c（引入维护负担）
- 对 grub2-2.12 核心文件的大规模改动

### 10.3 维护性评估

**代码复杂度降低**：
- 减少 ~2000 行（移除自定义 TPM2 库）
- 新增 ~1500 行（TLCP 核心改造后）
- **净减少** ~500 行代码

**外部依赖**：
- **移除**：custom TPM2 command library 依赖
- **复用**：grub2-2.12 内置 EFI TPM2 support
- **新增**：无（预期不需要新外部库）

**向前兼容**：
- 与 grub2-2.12 官方升级路径一致
- 无 fork 维护问题
- 便于后续升级到 grub2-2.13+ （若需要）

---

## 附录 A：关键数据结构参考

### Preboot Hook 数据结构
```c
// grub-core/commands/boot.c, 行 44-51
struct grub_preboot {
  grub_err_t (*preboot_func) (int flags);
  grub_err_t (*preboot_rest_func) (void);
  grub_loader_preboot_hook_prio_t prio;
  struct grub_preboot *next;
  struct grub_preboot *prev;
};
```

### EFI TPM2 Protocol
```c
// include/grub/efi/tpm.h, 行 152-193
struct grub_efi_tpm2_protocol {
  grub_efi_status_t (*get_capability)(...);
  grub_efi_status_t (*get_event_log)(...);
  grub_efi_status_t (*hash_log_extend_event)(...);
  grub_efi_status_t (*submit_command)(...);
  grub_efi_status_t (*get_active_pcr_banks)(...);
  grub_efi_status_t (*set_active_pcr_banks)(...);
  grub_efi_status_t (*get_result_of_set_active_pcr_banks)(...);
};
```

---

## 附录 B：grub2-2.02 vs 2.12 API 映射表

| 功能 | grub2-2.02 | grub2-2.12 | 迁移策略 |
|------|-----------|-----------|--------|
| TPM 度量 | `tpm2_pcrextend()` (custom) | `grub_tpm_measure()` | 直接调用 2.12 API |
| TPM 查询 | 自定义 TPM2 startup | `grub_efi_locate_handle()` + EFI TPM2 | 改为 EFI 标准方式 |
| 启动前验证 | 硬编码在 boot 命令 | preboot hook framework | 改为 hook 注册 |
| SHA256 | 自带 (tlcp_sha256.c) | 未内置，可复用自带 | 直接复用 |
| AES-CBC | 自带 (tlcp_aes.c) | 无，需保留自带 | 直接复用 |

---

**文档完成日期**：2026-04-02  
**审查状态**：待架构评审  
**建议下一步**：原型实现 Patch 1（密码库） + Patch 5（Makefile）进行可行性验证

