# iTrustMidware TLCP 联合验证方案

## 验证目标

验证 tlcptool（用户态策略部署）与 grub2-2.12（启动时完整性校验）联动的端到端正确性：
- tlcptool 部署的 TPM 策略能被 GRUB 正确识别
- PCR 度量值变化导致 GRUB Unseal 失败，触发口令回退
- 口令回退流程正常工作
- 文件策略（无 TPM）回退正常工作

---

## 前置条件

| 项目 | 要求 |
|------|------|
| 测试机 | UEFI 固件 + TPM 2.0（物理机或 QEMU+swtpm） |
| 操作系统 | KOS/Anolis，已安装 tlcptool 和 grub2-2.12（含 TLCP patch） |
| 权限 | root |
| 工具 | `tpm2-tools`（辅助调试）、`openssl`（口令加解密验证） |

### QEMU 测试环境搭建

```bash
# 安装 swtpm（软件 TPM）
dnf install swtpm swtpm-tools

# 初始化 swtpm 状态目录
mkdir -p /tmp/swtpm && swtpm_setup --tpm2 --tpmstate /tmp/swtpm --overwrite

# 启动 swtpm
swtpm socket --tpm2 --tpmstate dir=/tmp/swtpm \
    --ctrl type=unixio,path=/tmp/swtpm.sock \
    --log level=20 --daemon

# QEMU 启动（附 TPM 设备）
qemu-system-x86_64 \
    -enable-kvm -m 4G \
    -drive if=virtio,file=disk.img,format=qcow2 \
    -chardev socket,id=chrtpm,path=/tmp/swtpm.sock \
    -tpmdev emulator,id=tpm0,chardev=chrtpm \
    -device tpm-tis,tpmdev=tpm0 \
    -bios /usr/share/edk2/x64/OVMF.fd
```

---

## 验证用例

### 用例 1：审计策略部署与 GRUB 识别

**目的**：验证 `deploy_audit_policy()` → GRUB `grub_tpm_policy_state()` 联动。

```bash
# 步骤 1：确认 TPM 可用
tpm2_getcap properties-fixed | grep TPMVersion

# 步骤 2：部署审计策略（tlcptool）
tlcptool --deploy-audit
# 预期输出：deploy audit policy success

# 步骤 3：验证 TPM 资源创建
tpm2_getcap handles-persistent | grep -E "0x81010100|0x81010101"
# 预期：两个 handle 均出现

tpm2_nvlist | grep 0x01800100
# 预期：NV index 出现

tpm2_nvread --index 0x01800100 --size 4 | xxd
# 预期：01 00 00 00（审计策略值 = 1，大端序）

# 步骤 4：验证状态文件
ls -la /boot/hardware_state.bin /boot/software_state.bin /boot/policy.bin
# 预期：三个文件均存在，非空

# 步骤 5：重启，观察 GRUB 日志
# 在 GRUB 串口日志中应看到：
#   [tlcp] policy state: AUDIT
#   [tlcp] hardware integrity: OK
#   [tlcp] software integrity: OK
# 正常进入系统
```

**通过标准**：系统正常启动，无口令提示。

---

### 用例 2：监督策略部署与口令回退

**目的**：验证监督策略下完整性失败时的口令提示。

```bash
# 步骤 1：部署监督策略
tlcptool --deploy-supervisory
# 预期：deploy supervisory policy success

# 步骤 2：导出口令（备份）
tlcptool --export-passphrase > /root/passphrase.txt
cat /root/passphrase.txt
# 预期：硬件口令和软件口令各一行

# 步骤 3：破坏软件状态文件，模拟完整性失败
dd if=/dev/urandom bs=1 count=16 of=/boot/software_state.bin seek=0 conv=notrunc

# 步骤 4：重启，观察 GRUB 行为
# 预期 GRUB 输出：
#   *********************************************
#   *  Host OS Kernel&Initrd Has been Broken!   *
#   *********************************************
#   Enter passphrase: _
# 输入正确口令后正常启动

# 步骤 5：输入错误口令验证拒绝
# 输入错误口令，预期重新提示，不进入系统
```

**通过标准**：完整性失败触发一次口令提示（不重复）；正确口令后正常启动；错误口令循环提示。

---

### 用例 3：PCR 值变化导致 Unseal 失败

**目的**：验证 PCR 状态变更后 Unseal 失败，触发口令回退。

```bash
# 步骤 1：修改 host_st_configure.xml（影响 PCR 12）
echo "<extra/>" >> /boot/host_st_configure.xml

# 步骤 2：重启，观察 PCR 12 变化
# GRUB 会将新的 host_st_configure.xml 内容 extend 到 PCR 12
# 软件密钥封装时的 PCR 12 值与当前不同 → Unseal 失败

# 预期 GRUB 输出：
#   *  Host OS Kernel&Initrd Has been Broken!  *
#   Enter passphrase: _

# 恢复
sed -i '/<extra\/>/d' /boot/host_st_configure.xml
tlcptool --update-software  # 用新 PCR 12 值重新封装软件密钥
```

**通过标准**：PCR 变化 → Unseal 失败 → 口令回退；更新策略后恢复正常。

---

### 用例 4：无 TPM 场景（文件策略回退）

**目的**：验证 TPM 不可用时走文件策略路径。

```bash
# 方法 A：QEMU 不加 TPM 设备重启，GRUB 自动走文件路径
# 方法 B：移除 /dev/tpm0 设备（测试机）

# 预期：GRUB 读取 /boot/policy.bin，进入文件策略验证
# 口令回退路径与用例 2 一致
```

---

### 用例 5：PCR 12 度量验证

**目的**：验证 GRUB 正确将 `host_st_configure.xml` extend 到 PCR 12。

```bash
# 步骤 1：启动前记录 PCR 12 基准值（用 swtpm 时从日志获取）
tpm2_pcrread sha256:12

# 步骤 2：手动计算 host_st_configure.xml 的期望 PCR 12 值
CONTENT=$(cat /boot/host_st_configure.xml)
FILE_HASH=$(echo -n "$CONTENT" | openssl dgst -sha256 -binary)
CURRENT_PCR=$(tpm2_pcrread sha256:12 -o /tmp/pcr12_before.bin)
# PCR_NEW = SHA256(PCR_CURRENT || FILE_HASH)
cat /tmp/pcr12_before.bin <(echo -n "$CONTENT" | openssl dgst -sha256 -binary) | \
    openssl dgst -sha256

# 步骤 3：重启后读取 PCR 12
tpm2_pcrread sha256:12

# 预期：PCR 12 值与计算期望值一致
```

---

### 用例 6：策略更新验证

**目的**：验证 `update_audit_policy()` / `update_supervisory_policy()` 在 PCR 变化后更新封装。

```bash
# 场景：内核升级后 PCR 8/9 变化，需更新软件密钥封装
dnf update kernel
# 重启到新内核后：
tlcptool --update-software
# 预期：用当前 PCR 8/9/12 值重新封装软件密钥（handle 0x81010100）

# 验证：再次重启，软件完整性校验通过
```

---

## 快速诊断命令

```bash
# 查看 TPM 策略资源
tpm2_getcap handles-persistent
tpm2_nvlist

# 读取策略状态（0x01800100 的值）
tpm2_nvread --index 0x01800100 --size 4 | xxd

# 验证状态文件格式（前 32 字节为 SHA256(key)）
xxd /boot/hardware_state.bin | head -4

# 测试 TPM 通信
tpm2_getrandom 8 | xxd

# GRUB 调试输出（需 debug build）
# 在 grub.cfg 中添加：set debug=tlcp
```

---

## 验证矩阵

| 用例 | 策略类型 | TPM 可用 | PCR 匹配 | 期望结果 |
|------|---------|---------|---------|---------|
| 1 | 审计 | 是 | 是 | 正常启动，无提示 |
| 2 | 监督 | 是 | 否（状态文件破坏） | 口令提示，输入正确后启动 |
| 3 | 审计 | 是 | 否（PCR 12 变化） | 口令提示 |
| 4 | 审计 | 否 | — | 文件策略，口令提示 |
| 5 | 任意 | 是 | — | PCR 12 值正确扩展 |
| 6 | 监督 | 是 | 是（策略更新后） | 正常启动 |
