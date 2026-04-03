# grub2 spec 修改说明

## 版本信息

- 基础版本：`grub2-2.12-21.kos5`（`/root/works/grub2-2.12-21.kos5.src.rpm`）
- TLCP 版本：`grub2-2.12-22`

---

## grub.patches 变更（SOURCE11）

在 `/root/rpmbuild/SOURCES/grub.patches` 末尾追加以下 9 个 patch 条目：

```
Patch2001: 0001-add-tlcp-trusted-boot-support.patch
Patch2002: 0002-fix-tlcp-api-compat-grub2-2.12.patch
Patch2003: 0003-tlcp-rewrite-grub2-2.12-arch.patch
Patch2004: 0004-tlcp-fix-header-self-contained.patch
Patch2005: 0005-tlcp-export-kernel-symbols-EXPORT-FUNC.patch
Patch2006: 0006-tlcp-replace-efi-call-macros-direct-calls.patch
Patch2007: 0007-tlcp-avoid-grub-tpm-measure-use-efi-tcg2-direct.patch
Patch2008: 0008-tlcp-guard-grub-tpm-present-platform.patch
Patch2009: 0009-tlcp-fix-code-review-issues.patch
```

以及对应的 `%patch` 应用行（在 `%do_common_setup` 宏内的适当位置）：

```
%patch -P 2001 -p1
%patch -P 2002 -p1
%patch -P 2003 -p1
%patch -P 2004 -p1
%patch -P 2005 -p1
%patch -P 2006 -p1
%patch -P 2007 -p1
%patch -P 2008 -p1
%patch -P 2009 -p1
```

> **注意**：上游已将 9 个 patch 合并为单一文件 `doc/tlcp-grub2-2.12.patch`。
> 在 spec 中可以只注册一个 patch（Patch2001），使用合并后的文件替代原有 9 个。

---

## 合并 patch 方式（推荐）

```
# grub.patches 中只需一行：
Patch2001: tlcp-grub2-2.12.patch

# %prep 中只需一行：
%patch -P 2001 -p1
```

将 `doc/tlcp-grub2-2.12.patch` 复制到 `/root/rpmbuild/SOURCES/` 即可。

---

## %changelog 追加

```
* Thu Apr 03 2026 iTrustMidware TLCP <tlcp@inspur.com> - 1:2.12-22
- Add TLCP trusted boot measurement based on grub2-2.12 native architecture
- Rewrite kern/tlcp.c and kern/efi/tlcp.c with grub_ prefix API and
  grub2-2.12 preboot-hook integration
- Replace efi_call_X macros with direct EFI protocol method calls
- Integrate with tlcptool policy deployment via TPM2 Unseal (PCR binding)
- Fix: unaligned pointer cast, TPM session leak, double passphrase prompt,
  dirty error state, stack key zeroing, file size truncation (6 issues)
```

---

## src.rpm 重新打包

```bash
# 将合并 patch 放入 SOURCES
cp doc/tlcp-grub2-2.12.patch /root/rpmbuild/SOURCES/

# 打包 src.rpm
cd /root/rpmbuild
rpmbuild -bs SPECS/grub2.spec

# 输出在
ls SRPMS/grub2-2.12-22.*.src.rpm
```

---

## patch 应用顺序说明（9 个独立 patch 时）

| 编号 | 文件 | 作用 |
|------|------|------|
| 2001 | `0001-add-tlcp-trusted-boot-support.patch` | 初始 TLCP 框架：头文件、TPM2 命令栈、boot.c 集成、Makefile |
| 2002 | `0002-fix-tlcp-api-compat-grub2-2.12.patch` | 修正 2.12 API 兼容性（去掉旧式 TCTI 头引用） |
| 2003 | `0003-tlcp-rewrite-grub2-2.12-arch.patch` | 重写 kern/efi/tlcp.c、kern/tlcp.c 适配 2.12 grub_ 风格 |
| 2004 | `0004-tlcp-fix-header-self-contained.patch` | tlcp.h 添加 err.h/types.h，修复独立预处理错误 |
| 2005 | `0005-tlcp-export-kernel-symbols-EXPORT-FUNC.patch` | 为 5 个公开 API 添加 EXPORT_FUNC()，修复 moddep 错误 |
| 2006 | `0006-tlcp-replace-efi-call-macros-direct-calls.patch` | tpm2tis.c 去掉 efi_call_2/5，改直接调用 |
| 2007 | `0007-tlcp-avoid-grub-tpm-measure-use-efi-tcg2-direct.patch` | 实现内核级 grub_tlcp_efi_measure()，避免依赖 tpm 模块 |
| 2008 | `0008-tlcp-guard-grub-tpm-present-platform.patch` | boot.c 加 EFI/ieee1275 平台宏保护，修复 i386-pc 构建 |
| 2009 | `0009-tlcp-fix-code-review-issues.patch` | 修复 6 个代码审查问题（安全/可靠性/可移植性） |
