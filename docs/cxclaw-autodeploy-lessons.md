# 交易系统自动部署实战心得（Windows 自托管 runner · cxclaw）

> 沉淀时间：2026-09-10。场景：把 quant-core / trading 桥（Flask + IB + 掘金 gm + OKX）
> 从单机 winclaw 迁到 cxclaw，用 GitHub Actions self-hosted runner 做 push main 自动部署。
> 本文只记"真踩过的坑"和可复用结论，命令与文件以仓库现状为准。

## 1. 总体拓扑（跑通后的形态）

- 代码：`github.com/misyinhu/quant`、`github.com/misyinhu/trading`（私有仓），push main 触发部署。
- 部署机：cxclaw（Tailscale `100.82.238.11`，Windows），每个仓一个独立 runner 目录：
  - `C:\actions-runner`（life-compass，原有，勿动）
  - `C:\actions-runner-quant`（quant-core，标签 `cxclaw,quant-core`）
  - `C:\actions-runner-trading`（trading 桥，标签 `cxclaw,trading-bridge`）
  - runner 用"计划任务 AtLogon"保活（`Register-ScheduledTask`，InteractiveToken），
    不用 Windows 服务也行；同一台机可以并存多个 runner，关键是**每个仓一个目录、一个名字、一套标签**。
- 运行时：PM2 托管两个 Python 服务
  - `quant-server` → uvicorn :8005，代码在 `D:\projects\quant`
  - `trading-bridge` → `notify/webhook_bridge.py 5002`，代码在 `D:\projects\trading`
- 本机依赖：IB Gateway `127.0.0.1:4002`、掘金终端 `gmterm-serv` `127.0.0.1:7001`（goldminer3）。
- 出网：cxclaw 无国际出口，上游代理走另一台机（Mac Clash Party `100.80.148.2:7890`，Tailscale 内网）。

**结论：交易类系统的"部署成功"不止是代码更新，而是 代码 + 进程 + 柜台/终端会话 + 出网 + 密钥 五件事同时成立。**

## 2. 部署工作流的正确写法（.github/workflows/deploy.yml）

### 2.1 只同步运行时需要的目录，绝不在部署目录根上 robocopy /MIR

- 逐目录 `robocopy src\<dir> dst\<dir> /MIR`，白名单显式列（trading 桥：
  `notify client config ctp_client gm_client okx_client account orders`）。
- **绝不**同步仓库根到 `D:\projects\trading` 根：会冲掉本机专属文件
  （`.streamlit/secrets.toml`、`ecosystem.config.js`、日志、缓存、`data/`）。
  这几类都"按机器不同"，必须留在部署机、由 workflow 只在缺失时生成。
- 排除 `__pycache__` / `*.pyc` / `.pytest_cache`。
- robocopy 退出码 `0/1` 都是成功（1=有文件复制），只有 `>=8` 才是错；判断后立刻
  `$global:LASTEXITCODE = 0`，否则它会污染后续步骤（quant 部署时踩过，把成功当失败）。

### 2.2 Windows runner 上的 shell：默认是 Windows PowerShell 5.1，没有 pwsh

- self-hosted Windows runner 默认 shell 就是 PowerShell 5.1，**不要写 `shell: pwsh`**
  （除非确认装了 PowerShell 7），否则报 `pwsh: command not found`。
- PS 5.1 的坑：
  - 原生命令（pm2/git）把提示写进 **stderr**，在 GHA 注入的
    `ErrorActionPreference=Stop` 下会被当成终止错误。对策：用 `cmd /c "..."` 承接，
    例如 `cmd /c "pm2 restart x || (pm2 start ecosystem.config.js && pm2 save)"`。
  - 用 here-string 生成 JS 文件时，结束符必须在行首且与内容缩进自洽；缩进不对会让
    整个 YAML 字面块非法（run 在 actions 解析阶段就报"quoted scalar unexpected EOF"）。
    稳妥做法是用字符串数组 `@("line1","line2") -join "\`n" | Set-Content`。
  - 用 `& $python -m venv ...` 这类调用时，`$LASTEXITCODE` 要用 `try/catch` 包住
    探测命令，否则非零退出在 EAP=Stop 下直接终止整个 step。

### 2.3 部署 idempotent（幂等）：每次重跑结果一致

- venv 已存在不能跳过——可能建了但包装失败。判断标准是"能不能 import"，
  不是"目录在不在"：`gm_env\Scripts\python.exe -c "import gm"` 失败就重建/补装。
- PM2 进程已存在则 restart（带 `--update-env`），不存在才 start；重启后 `pm2 save`。
- `ecosystem.config.js` 只在缺失时生成（它是 per-machine 文件，cwd C:/ vs D:/ 不同）。

### 2.4 健康检查 + smoke test 必须打到"真实外部依赖"

- 健康检查要轮询（30 次 × 2s），给 uvicorn/flask + ib_insync 冷启动时间。
- smoke 不能只打 `/health`，要打**真实下游**：gm 历史、OKX 行情、IB 合约。
  - 关键细节：gm `/api/gm/history` **必须带 start_time/end_time**，不带日期会 500
    （`run(mode=1)` 框架下空窗口行为不确定），smoke 要带真实日期范围。
- smoke 失败不要 `exit 1` 整个 run：它是"观察哨"，打印 PASS/FAIL 即可；
  真正卡上线的是健康检查（进程没起来）。

## 3. 一台机多仓 runner：deploy key 与 git 出网

这是本次最绕的一块，单独讲。

### 3.1 一个仓一把 deploy key，不能共用

- GitHub deploy key 是**仓库级**的：一把 key 只能访问一个仓。
- 更隐蔽的坑：SSH 在**认证层**先接受"第一把能登录 github.com 的 key"，再判断该 key
  对目标仓有没有权限。多把 key 放一起，git 不会自动"换下一把"，于是 B 仓 checkout
  报 `Could not read from remote repository`，看着像权限问题其实是 key 选错。
- 解法（cxclaw 上验证可行）：
  - 每仓一对 key：`id_ed25519_quant`、`id_ed25519_trading`，公钥分别加到对应仓的
    Settings → Deploy keys（只读即可，CI 不需要 push）。
  - 全局 `~/.gitconfig` 用 `includeIf` 按 runner 工作目录切 key：
    ```ini
    [includeIf "gitdir:C:/actions-runner-quant/_work/"]
        path = C:/Users/Apple/.gitconfig-quant
    [includeIf "gitdir:C:/actions-runner-trading/_work/"]
        path = C:/Users/Apple/.gitconfig-trading
    ```
    每个分片文件里：
    ```ini
    [core]
        sshCommand = ssh -i C:/Users/Apple/.ssh/id_ed25519_xxx -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
    ```

### 3.2 首次 clone 时 includeIf 还没生效 → 在 job 里钉死 GIT_SSH_COMMAND

- actions/checkout 是**全新 clone**，此时还没有 `.git` 目录，`includeIf.gitdir:` 不命中，
  系统又配了 `url.git@github.com:.insteadOf https://github.com/`，于是用错默认 key。
- 解法：在 deploy job 级 env 显式指定：
  ```yaml
  env:
    GIT_SSH_COMMAND: ssh -i C:/Users/Apple/.ssh/id_ed25519_trading -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new
  ```

### 3.3 cxclaw 没有国际出口，github 走 SSH(22) 不走 https(443)

- 现象：`git fetch https://github.com` 报 `Recv failure: Connection was reset` / 443 连不上。
- cxclaw 上 `ssh -T git@github.com`（22 端口）是通的，所以保留系统级
  `insteadOf https→ssh`，配合 3.1/3.2 的 key 选择即可；PyPI/OKX 等 https 需求单独走代理。
- 排查顺序建议：先看 runner 列表（`/repos/{o}/{r}/actions/runners` 是否 online），
  再看失败 job 的具体 step 日志（job logs API 直接是纯文本，不是 zip），
  区分"没 runner / checkout 失败 / 同步失败 / 依赖失败 / 起进程失败 / 健康检查失败"，
  每一层的修法完全不同。

## 4. Python 依赖与国内网络

- 部署机两个 Python 环境要分清：
  - 系统 Python（`Python312`）跑桥本体：`flask requests pyyaml ib_insync schedule psutil`。
  - **独立 venv** `C:\projects\gm_env` 跑掘金 SDK：`gm==3.0.186` + `protobuf==3.20.3`
    （gm 要求 protobuf <4，必须隔离，否则污染主环境）。
- cxclaw 直连 PyPI 不通（`No matching distribution found`），用清华镜像：
  `-i https://pypi.tuna.tsinghua.edu.cn/simple`。装包这步要放进 workflow 而不是手动，
  换机能一键重建。
- worker 文件要随部署拷进 venv 目录：
  `Copy-Item gm_client\gmsim_worker.py C:\projects\gm_env\gmsim_worker.py`
  （gm 的 `run(filename=...)` 在 cwd 找模块，不是从仓库目录找）。

## 5. 代理：要"显式、分层、可隔离"，别相信系统环境

这是交易桥最容易反复出问题的地方。

### 5.1 程序里不要无条件删代理环境变量，也不要无条件继承

- 旧代码为 winclaw 写死"启动即 `os.environ.pop` 掉所有 proxy + 某些请求硬编码
  `127.0.0.1:7890`"，搬到无出口的 cxclaw 后 OKX 全挂。
- 正解是一个**显式开关**：`OUTBOUND_PROXY`。
  - 桥启动时先清空 proxy，再在 `OUTBOUND_PROXY` 非空时统一注入大小写两套
    `HTTP_PROXY/HTTPS_PROXY/http_proxy/https_proxy`（Windows 下 requests 对大小写敏感，
    只设大写不生效）。
  - 同时给 `NO_PROXY/no_proxy` 放行本机与 Tailscale 段，保证 IBGW/掘金终端/内网不走代理。
- requests 默认 `trust_env=True` 会读环境变量；urllib 的 `ProxyHandler` 要单独
  传 `{}`（无代理）或 `{"https": _outbound_proxy}`，不能写死 127.0.0.1。

### 5.2 原生 SDK 子进程必须剥离代理

- 掘金 gm 的 C 原生层（gmsdk.dll）在带 `HTTP(S)_PROXY` 的环境里会直接崩
  （exit code `3221225477` = 0xC0000005 访问违例），而且它连的是本机
  `localhost:7001`，本就不该走代理。
- 桥用子进程跑 gm 时，构造 `env = dict(os.environ)` 后**显式 pop 掉所有代理变量**再传：
  这是"主进程走外网代理、子进程直连本机柜台"的分层隔离，必须在代码里保证而不是靠记得配。

### 5.3 上游代理本身要允许 Tailscale 内网访问

- Mac 的 Clash Party 默认只监听 127.0.0.1，cxclaw 用不了。需要开"允许局域网连接"
  （allow-lan），并在 mihomo 配置里持久化 `allow-lan: true`，否则 Clash 重启后设置被还原，
  cxclaw 的 OKX 会"昨天好好的今天全断"。

## 6. 密钥与账户：登录名 ≠ 交易账号

- 密钥不入库：放部署机 `D:\projects\trading\.streamlit\secrets.toml`
  （`chmod 600`），workflow 同步白名单不含 `.streamlit`，不会被覆盖；
  程序读密钥顺序：环境变量 > secrets.toml。
- **掘金的坑**：用户给的 `17898878308/misyinhu`、`misyinhu` 是**掘金登录账号**，
  不是交易资金账号。`get_cash(account_id="misyinhu")` 不报错但永远返回空。
  真正的交易账号是一个 **UUID**（形如 `0080a3eb-a5df-11f1-a7e7-...`）。
  - 找法：掘金终端先在界面里登录"模拟交易"，再看终端日志
    `~/.goldminer3/logs/<时间戳>/main.log`，搜 `account-trade/login` 或
    `初始化账户: ["<uuid>"]`。
  - 拿到 UUID 写进 `GM_ACCOUNT`，`get_cash` 才返回真实资金（本次 100 万模拟本金）。
  - 前提：掘金终端里模拟交易要保持登录；终端登出后资金/下单返空（历史行情不受影响）。
- OKX 报 `50101 APIKey does not match current environment`：是 sim/live key 用反了
  （模拟 key 必须带 `x-simulated-trading: 1`，由 SDK flag=1 处理），确认读的是
  `OKX_SIM_*` 而不是 `OKX_LIVE_*`。本次还顺带发现部署漏同步 `okx_client/`，
  远端在跑旧代码——**加了新代码目录，必须加进 workflow 的同步白名单**。

## 7. PM2 与 Windows 的几个点

- 改了 `ecosystem.config.js` 的 env 后，`pm2 restart --update-env` 对"已存在进程"
  有时不生效（保留旧环境）。最稳是 `pm2 delete <name>` 再 `pm2 start ecosystem.config.js`
  然后 `pm2 save`。验证用 `pm2 env <id>` 而不是只看 `pm2 list`。
- `pm2 jlist` 在 PowerShell 里别管道给 `ConvertFrom-Json`（NODE 环境里 USERNAME/username
  大小写重复键会让 PS 解析崩）；判断服务在不在，直接看 restart/start 的退出码。
- 部署机重启后 PM2 要能自拉起（`pm2 save` + 相应 resurrect 机制）；runner 靠计划任务
  AtLogon 自启。两个都要验"重启机器后是否自动回来"。

## 8. 可复用的发布顺序（checklist）

1. 本地改完，**先验证 YAML 合法**（`python -c "import yaml; yaml.safe_load(open(...))"`）
   和 JS 生成片段、命令在 PS5.1 语法下成立。
2. commit/push（本机若也走代理，git push 临时带 `HTTPS_PROXY=127.0.0.1:7890`）。
3. Actions 跑完看结论；失败按 step 定位：runner 在线 → checkout(key/网络) →
   robocopy(退出码) → pip(镜像) → PM2(EAP/旧环境) → 健康检查 → smoke。
4. 部署机直连 smoke：gm 历史(带日期)、gm 账户(UUID)、OKX 行情+账户、IB 历史、`/health/full`。
5. 下游（quant-agent）端点收口到一个配置文件 `config/services.yaml`，
   优先级：环境变量 > yaml > 代码兜底；所有独立脚本启动时引导加载，别各写各的 IP。
6. 换/迁机器时，需要人工备齐的五件套先列清单：runner 注册(key+includeIf+计划任务)、
   系统 Python 依赖、隔离 venv、PM2 ecosystem、secrets.toml + 柜台/终端登录态。

## 9. 一句话经验

> 交易系统的自动部署，本质是"让一台陌生机器在没有你盯着时，也能稳定连上一堆
> 有状态的外部柜台"。CI 能可靠更新的只有**无状态的代码**；凡是**有状态的东西**
> （密钥、交易账号 UUID、IB/掘金终端登录会话、代理准入、per-machine 配置）都要显式外置、
> 幂等探测、并在 smoke 里真正打一次下游——否则绿勾只代表文件复制成功，不代表能交易。
