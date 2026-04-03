# grub2-2.02 vs grub2-2.12 架构升级对比

## 1. 模块加载与符号管理

| 维度 | grub2-2.02 | grub2-2.12 |
|------|-----------|-----------|
| 模块依赖解析 | `moddep.lst` 静态列表 | 动态符号提取，`kernel_syms.lst` 由 `EXPORT_FUNC(name)` 宏在预处理阶段生成 |
| 内核符号导出 | 直接声明函数即可 | 必须用 `EXPORT_FUNC()` 包裹声明，否则 moddep 报 "not defined" |
| 头文件预处理 | 依赖上下文 include | `KERNEL_HEADER_FILES` 被独立预处理（`-DGRUB_SYMBOL_GENERATOR=1`），头文件必须自包含 |

**TLCP 影响**：`include/grub/tlcp.h` 必须显式 `#include <grub/err.h>` 和 `<grub/types.h>`；所有公开 API 必须用 `EXPORT_FUNC()` 包裹。

---

## 2. EFI 协议调用方式

| 维度 | grub2-2.02 | grub2-2.12 |
|------|-----------|-----------|
| 调用宏 | `efi_call_N(proto->method, args...)` | 已删除，直接调用：`proto->method(args...)` |
| 调用约定 | 需 `efi_call_X` 做 ABI 桥接 | EFI 方法指针声明带 `__grub_efi_api` 属性，直接可调 |

**TLCP 影响**：`grub-core/kern/efi/tpm2tis.c` 中 `tpm->get_capability()` 和 `tpm->submit_command()` 从 `efi_call_2/5` 改为直接调用。

---

## 3. 启动钩子（Preboot Hook）机制

| 维度 | grub2-2.02 | grub2-2.12 |
|------|-----------|-----------|
| 集成方式 | 直接修改 `grub_cmd_boot()` 主体 | 注册 preboot hook：`grub_loader_register_preboot_hook()` |
| 可扩展性 | 侵入性强，升级时易冲突 | 解耦，模块可独立注册 hook |
| TLCP 集成点 | 嵌入 boot.c 函数体 | `grub_cmd_boot()` 在调用 loader 前调用 TLCP 检查（兼容两种风格） |

---

## 4. TPM 度量函数可用性

| 维度 | grub2-2.02 | grub2-2.12 |
|------|-----------|-----------|
| `grub_tpm_measure()` | 内核符号，内核代码可直接调用 | 移到 `tpm` 模块（`commands/efi/tpm.c`），内核代码不可直接调用 |
| PCR 扩展方法 | 调用 `grub_tpm_measure()` | 内核代码需直接使用 `EFI_TCG2_PROTOCOL.hash_log_extend_event()` |

**TLCP 影响**：实现 `grub_tlcp_efi_measure()`（在 `kern/efi/tlcp.c`）直接使用 EFI TCG2 协议，避免对 `tpm` 模块的依赖。

---

## 5. 平台条件编译

| 维度 | grub2-2.02 | grub2-2.12 |
|------|-----------|-----------|
| TPM 相关 API 可用性 | `grub_tpm_present()` 等在更多上下文可用 | 仅在 `GRUB_MACHINE_EFI` / `GRUB_MACHINE_IEEE1275` 时可用 |
| i386-pc 构建 | 构建失败较少见 | 需显式 `#if defined(GRUB_MACHINE_EFI) \|\| defined(GRUB_MACHINE_IEEE1275)` 保护 |

**TLCP 影响**：`grub-core/commands/boot.c` 中 `grub_tpm_present()` 调用必须在 EFI/ieee1275 平台宏保护下；非 EFI 平台跳过 TPM 检查，直接走文件策略。

---

## 6. 构建系统

| 维度 | grub2-2.02 | grub2-2.12 |
|------|-----------|-----------|
| 构建定义文件 | `Makefile.core.def` + 手动管理 | 同上，但模块注册语法略有不同 |
| AES/SHA 实现 | 可依赖外部模块 | TLCP 内部实现（`tlcp_aes.c`, `tlcp_sha256.c`）内联入内核，不依赖外部 crypto 模块 |

---

## 总结

grub2-2.12 在符号管理、EFI 调用、TPM 可用性上做了较大调整。TLCP 的移植核心工作：

1. `tlcp.h` 自包含 + `EXPORT_FUNC()` 装饰
2. 去除 `efi_call_X` 宏，改用直接协议调用
3. 实现内核级 `grub_tlcp_efi_measure()`，绕开 tpm 模块依赖
4. `grub_tpm_present()` 调用加平台宏保护
