# GRUB2 架构升级分析：2.02 → 2.12

**分析日期**：2026-04-03  
**分析范围**：grub2-2.02 与 grub2-2.12 在可信启动相关架构上的核心差异  
**目的**：为基于 grub2-2.12 重新实现 iTrustMidware TLCP 可信启动度量提供架构依据

---

## 一、总体架构对比

| 维度 | grub2-2.02 | grub2-2.12 | 影响评估 |
|------|-----------|-----------|---------|
| **启动扩展点** | 无框架，需直接修改 `grub_cmd_boot()` | 完整 preboot hook 优先级链表框架 | 2.12 通过 hook 注入，解耦彻底 |
| **TPM2 库** | 需自带 23 个 `.c` 文件的完整 TPM2 命令库 | 原生 `grub_efi_tpm2_protocol_t` EFI 接口 + `grub_tpm_measure()` | 2.12 消除了 TPM2 底层代码 |
| **EFI TPM 头文件** | 仅有基础 TPM1.2 结构 | 完整 TPM2 结构体与方法指针 | 2.12 官方支持 TPM2 |
| **模块系统** | 相同 Makefile.core.def 语法 | 相同语法，增加 EFI 平台条件编译支持 | 语法兼容，直接复用 |
| **PCR 扩展接口** | 自定义 TPM2 命令封装 | 标准 `grub_tpm_measure(buf, size, pcr, desc)` | 2.12 接口更简洁 |
| **EFI Protocol 获取** | 自实现 locate/open 逻辑 | `grub_efi_locate_handle()` / `grub_efi_open_protocol()` | 2.12 有标准封装 |
| **原始 TPM2 命令** | 自定义每条命令的完整序列化 | `tpm2_protocol->submit_command(in_size, in_buf, out_size, out_buf)` | 2.12 通过 EFI 协议传递原始命令 |

---

## 二、关键架构变化详解

### 2.1 Preboot Hook 框架（新增）

**grub2-2.02 的做法：**  
直接在 `grub_cmd_boot()` 函数体内插入 TLCP 验证逻辑，属于侵入式修改，与 boot 命令高度耦合。

**grub2-2.12 的机制：**  
引入优先级链表式 preboot hook 框架（`grub-core/commands/boot.c`，行 44–126）。

**数据结构：**
```c
struct grub_preboot {
    grub_err_t (*preboot_func)(int flags);    /* 启动前执行 */
    grub_err_t (*preboot_rest_func)(void);    /* 启动回滚时执行 */
    grub_loader_preboot_hook_prio_t prio;     /* 执行优先级 */
    struct grub_preboot *next, *prev;
};
```

**优先级枚举（从高到低执行）：**
```c
GRUB_LOADER_PREBOOT_HOOK_PRIO_FIRST  = 1000  /* 最先执行 */
GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL = 0     /* 默认优先级 */
GRUB_LOADER_PREBOOT_HOOK_PRIO_LAST   = -1000 /* 最后执行 */
```

**执行流程（`grub_loader_boot()`）：**
1. 检查是否加载了内核
2. 调用 `grub_machine_fini()`（停用机器驱动）
3. **正序**遍历链表，依次调用每个 hook 的 `preboot_func(flags)`
4. 执行实际的 boot loader
5. 如 boot 失败，**逆序**遍历链表，调用 `preboot_rest_func()` 回滚

**注册 / 注销 API：**
```c
/* 注册 hook，返回 handle（用于注销） */
struct grub_preboot *grub_loader_register_preboot_hook(
    grub_err_t (*preboot_func)(int flags),
    grub_err_t (*preboot_rest_func)(void),
    grub_loader_preboot_hook_prio_t prio);

/* 注销 hook */
void grub_loader_unregister_preboot_hook(struct grub_preboot *hnd);
```

**与 2.02 的本质区别：**  
2.12 中任何需要在启动前执行的功能都应注册为 hook，而不是修改 boot 命令本身，这是推荐且被维护的扩展点。

---

### 2.2 EFI TPM2 协议原生支持（架构性升级）

**grub2-2.02：**  
需要自带完整的 TPM2 TSS 命令库（TPM2_StartAuthSession、TPM2_PolicyPCR、TPM2_Unseal、TPM2_FlushContext 等约 23 个文件），直接通过 EFI 系统表手动 locate/open TPM2 协议。

**grub2-2.12：**  
原生定义 `grub_efi_tpm2_protocol_t`（`include/grub/efi/tpm.h`，行 152–193）：

```c
struct grub_efi_tpm2_protocol {
    /* 查询 TPM 支持的哈希算法、PCR 数量等能力 */
    grub_efi_status_t (*get_capability)(
        EFI_TCG2_PROTOCOL *this,
        EFI_TCG2_BOOT_SERVICE_CAPABILITY *cap);

    /* 获取事件日志（EFI TCG2 标准事件日志） */
    grub_efi_status_t (*get_event_log)(...);

    /* 哈希 + 写日志 + 扩展 PCR（三合一，标准事件日志格式） */
    grub_efi_status_t (*hash_log_extend_event)(
        EFI_TCG2_PROTOCOL *this,
        grub_efi_uint64_t flags,
        grub_efi_physical_address_t data_to_hash,
        grub_efi_uint64_t data_to_hash_len,
        EFI_TCG2_EVENT *efi_tcg_event);

    /* 向 TPM 发送任意原始命令（用于 Unseal 等非标准操作） */
    grub_efi_status_t (*submit_command)(
        EFI_TCG2_PROTOCOL *this,
        grub_efi_uint32_t input_param_block_size,
        grub_efi_uint8_t *input_param_block,
        grub_efi_uint32_t output_param_block_size,
        grub_efi_uint8_t *output_param_block);

    /* 获取/设置活跃的 PCR bank（SHA1/SHA256/SM3 等） */
    grub_efi_status_t (*get_active_pcr_banks)(...);
    grub_efi_status_t (*set_active_pcr_banks)(...);
    grub_efi_status_t (*get_result_of_set_active_pcr_banks)(...);
};
```

**获取协议实例的标准模式**（来自 `grub-core/commands/efi/tpm.c`）：
```c
static grub_efi_handle_t tpm_handle;
static grub_efi_tpm2_protocol_t *tpm2;

static grub_err_t grub_tpm2_handle_find(void) {
    grub_efi_handle_t *handles;
    grub_efi_uintn_t num_handles;

    /* 1. 按协议 GUID 枚举所有匹配 handle */
    handles = grub_efi_locate_handle(GRUB_EFI_BY_PROTOCOL,
                                      &grub_efi_tpm2_guid,
                                      NULL, &num_handles);
    if (!handles || num_handles == 0)
        return GRUB_ERR_UNKNOWN_DEVICE;

    /* 2. 打开第一个 handle 获取协议指针 */
    tpm2 = grub_efi_open_protocol(handles[0],
                                   &grub_efi_tpm2_guid,
                                   GRUB_EFI_OPEN_PROTOCOL_GET_PROTOCOL);
    tpm_handle = handles[0];
    grub_free(handles);
    return GRUB_ERR_NONE;
}
```

---

### 2.3 标准 PCR 度量接口

**grub2-2.02：** 无统一度量接口，各处自行调用 TPM2 命令。

**grub2-2.12：** 提供统一的 `grub_tpm_measure()` 函数（`include/grub/tpm.h`）：

```c
/* 对指定数据计算哈希并扩展到 PCR，同时写入事件日志 */
grub_err_t grub_tpm_measure(
    unsigned char *buf,    /* 待度量数据 */
    grub_size_t size,      /* 数据长度 */
    grub_uint8_t pcr,      /* 目标 PCR 编号 */
    const char *description /* 事件描述字符串 */
);
```

实现位于 `grub-core/commands/efi/tpm.c`，内部使用 `hash_log_extend_event`。

---

### 2.4 EFI 通用工具函数

grub2-2.12 提供完整的 EFI 辅助函数（`include/grub/efi/efi.h`）：

```c
/* 按 GUID/Handle 枚举协议实例 */
grub_efi_handle_t *grub_efi_locate_handle(
    grub_efi_locate_search_type_t search_type,
    grub_efi_guid_t *protocol,
    void *search_key,
    grub_efi_uintn_t *num_handles);

/* 打开指定 handle 上的协议 */
void *grub_efi_open_protocol(
    grub_efi_handle_t handle,
    grub_efi_guid_t *protocol,
    grub_efi_uint32_t attributes);
```

关键常量（`include/grub/efi/api.h`）：
```c
GRUB_EFI_BY_PROTOCOL               /* locate_handle 按 GUID 搜索 */
GRUB_EFI_OPEN_PROTOCOL_GET_PROTOCOL /* open_protocol 只读获取 */
```

---

## 三、TPM2 原始命令序列（Unseal 流程）

在 2.12 中，对于 EFI 协议未封装的 TPM2 命令（如 PolicyPCR、Unseal），需通过 `submit_command` 发送原始 TPM2 命令包。

以下为 grub2-2.02 实现的参考序列（算法逻辑不变，命令格式符合 TPM2.0 规范）：

### 步骤 1：TPM2_StartAuthSession
```
目的：创建 Policy 会话（HMAC/Policy 授权）
输入：tpmKey=TPM_RH_NULL, bind=TPM_RH_NULL,
      sessionType=TPM_SE_POLICY, symmetric=TPM_ALG_NULL,
      authHash=TPM_ALG_SHA256
输出：sessionHandle（后续步骤使用）
```

### 步骤 2：TPM2_PolicyPCR
```
目的：将 PCR 状态绑定到 policy 会话
输入：policySession=<上一步的 sessionHandle>
      pcrDigest=<policy 部署时记录的 PCR 摘要>
      pcrs=<绑定的 PCR 列表>
输出：会话的 policyDigest 更新
```

### 步骤 3：TPM2_Unseal
```
目的：解封存储在 TPM 持久句柄中的密钥数据
输入：itemHandle=0x81010101（硬件密钥）或 0x81010100（软件密钥）
      auth=<policy 会话句柄>
输出：sensitiveData（解密密钥，用于解密 passphrase 文件）
```

### 步骤 4：TPM2_FlushContext
```
目的：清理 policy 会话，释放 TPM 资源
输入：flushHandle=<sessionHandle>
```

**PCR 绑定配置**（来自 iTrustMidware/TLCPTool/src/tpmmodule.c）：

| 密钥类型 | TPM 持久句柄 | 绑定 PCR | 度量内容 |
|---------|------------|---------|---------|
| 硬件密钥 | `0x81010101` | PCR 0,1,2,3,6,7 | BIOS 固件、设备配置、安全启动配置 |
| 软件密钥 | `0x81010100` | PCR 8,9,12 | Kernel、Initrd、GRUB 模块 |
| NV 索引 | `0x01800100` | — | 策略状态元数据 |

---

## 四、Makefile.core.def 模块定义

grub2-2.12 的模块定义语法与 2.02 完全兼容，EFI 平台专属模块示例：

```
module = {
  name = tlcp_measure;               /* 模块名（生成 tlcp_measure.mod） */
  common = kern/efi/tlcp_measure.c;  /* 通用源文件 */
  enable = efi_64;                   /* 仅在 EFI 64-bit 平台编译 */
  enable = efi_32;                   /* 可同时支持 EFI 32-bit */
};
```

模块通过 `GRUB_MOD_INIT` / `GRUB_MOD_FINI` 宏注册初始化和清理逻辑：

```c
GRUB_MOD_INIT(tlcp_measure) {
    /* 注册 preboot hook，优先级设为 NORMAL */
    tlcp_hook_handle = grub_loader_register_preboot_hook(
        tlcp_preboot_func,   /* 启动前执行 TLCP 验证 */
        tlcp_rest_func,      /* 启动失败时清理 */
        GRUB_LOADER_PREBOOT_HOOK_PRIO_NORMAL
    );
}

GRUB_MOD_FINI(tlcp_measure) {
    if (tlcp_hook_handle)
        grub_loader_unregister_preboot_hook(tlcp_hook_handle);
}
```

---

## 五、架构升级对 TLCP 实现的影响

### 5.1 不能直接迁移的原因

1. **扩展点变化**：2.02 通过侵入式修改 `grub_cmd_boot()` 实现 TLCP，2.12 必须改为 preboot hook 注册方式
2. **TPM2 库变化**：2.02 的 23 个 TPM2 命令文件在 2.12 中绝大多数由 EFI 协议原生提供，直接迁移会造成重复实现
3. **EFI API 变化**：`grub_efi_guid_t` 等类型名称变化，`grub_err_t` 错误码集合变化
4. **文件系统 API 变化**：`grub_fs` 结构体字段名称变化
5. **应用程序 PCR 常量**：`GRUB_APPLICAION_PCR` 等宏在 2.12 中已重命名或移除

### 5.2 基于 2.12 架构的实现策略

| 功能 | 2.02 实现方式 | 2.12 推荐方式 |
|------|-------------|-------------|
| 启动前验证 | 直接修改 `grub_cmd_boot()` | 注册 preboot hook |
| PCR 扩展 | 自定义 TPM2 命令 | `grub_tpm_measure()` |
| TPM2 Unseal | 自定义序列化命令 | `tpm2_protocol->submit_command()` |
| EFI 协议获取 | 自实现 locate/open | `grub_efi_locate_handle()` + `grub_efi_open_protocol()` |
| 状态验证逻辑 | 耦合在 boot 命令 | 独立模块，通过 hook 注入 |

---

## 六、关键源文件索引

| 功能 | grub2-2.02 源文件 | grub2-2.12 源文件 |
|------|-----------------|-----------------|
| Boot 主流程 | `grub-core/normal/main.c` | `grub-core/commands/boot.c` |
| Preboot Hook | 无 | `grub-core/commands/boot.c:44-126` |
| TPM EFI 协议 | 自定义（tlcp.c） | `grub-core/commands/efi/tpm.c` |
| TPM2 协议头 | 无/自定义 | `include/grub/efi/tpm.h:152-193` |
| 标准度量接口 | 无 | `include/grub/tpm.h` |
| EFI 工具函数 | 有（基础） | `include/grub/efi/efi.h`（更完整） |
| TLCP 实现（2.02） | `grub-core/kern/efi/tlcp.c` | 需重新实现 |
| TLCP 状态验证（2.02） | `grub-core/kern/tlcp.c` | 需重新实现 |
