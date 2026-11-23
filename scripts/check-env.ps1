# ============================================================
# BiliInsight 环境自检脚本
# 用法：powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check-env.ps1
# 作用：一键检测技术栈是否齐备，输出缺失项与下载路径
# 兼容：Windows PowerShell 5.1+ / PowerShell 7+（文件须以 UTF-8 BOM 保存）
# ============================================================

$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference    = 'SilentlyContinue'

function Write-Head($t) {
    Write-Host ""
    Write-Host ("=" * 66) -ForegroundColor DarkCyan
    Write-Host "  $t" -ForegroundColor Cyan
    Write-Host ("=" * 66) -ForegroundColor DarkCyan
}

# 安全地取命令版本：先把输出收进变量，避免管道过早中断导致挂起
function Get-CmdVersion($name, $arg) {
    if (-not (Get-Command $name -ErrorAction SilentlyContinue)) { return $null }
    try {
        $out = & $name $arg 2>&1 | Out-String
        $line = ($out -split "`r?`n" | Where-Object { $_.Trim() -ne '' } | Select-Object -First 1)
        if (-not $line) { $line = '(已安装)' }
        return $line.Trim()
    } catch {
        return '(已安装)'
    }
}

# 按候选路径探测不在 PATH 上的程序
function Find-Exe($patterns) {
    foreach ($p in $patterns) {
        $r = Get-Item $p -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($r) { return $r }
    }
    return $null
}

$missing = @()

Write-Host ""
Write-Host "  BiliInsight 环境自检" -ForegroundColor White
Write-Host "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor DarkGray

# ------------------------------------------------------------
Write-Head "P0 - 必需（缺失则项目无法运行）"

# 注意：命令名与显示名分开，避免把 'Node.js' 当成可执行文件名
$p0 = @(
    @{ cmd='python';    show='Python';    arg='--version';  d='https://www.python.org/downloads/';                        note='后端运行环境 3.11+' },
    @{ cmd='node';      show='Node.js';   arg='--version';  d='https://nodejs.org/';                                      note='前端运行环境 18+' },
    @{ cmd='npm';       show='npm';       arg='--version';  d='随 Node.js 安装';                                           note='前端依赖管理' },
    @{ cmd='git';       show='git';       arg='--version';  d='https://git-scm.com/downloads';                            note='版本控制' },
    @{ cmd='mysql';     show='MySQL';     arg='--version';  d='https://dev.mysql.com/downloads/installer/';               note='主数据库（或改用 Docker）' },
    @{ cmd='redis-cli'; show='Redis';     arg='--version';  d='https://github.com/redis-windows/redis-windows/releases';  note='缓存/Broker（或 Docker/Memurai）' }
)

foreach ($t in $p0) {
    $ver = Get-CmdVersion $t.cmd $t.arg
    if ($ver) {
        Write-Host ("  [OK]      {0,-10} {1}" -f $t.show, $ver) -ForegroundColor Green
    } else {
        Write-Host ("  [MISSING] {0,-10} {1}" -f $t.show, $t.note) -ForegroundColor Red
        Write-Host ("            下载: {0}" -f $t.d) -ForegroundColor DarkYellow
        $missing += @{ n=$t.show; d=$t.d }
    }
}

# ------------------------------------------------------------
Write-Head "P1 - 强烈建议（影响开发效率 / 功能完整性）"

$dv = Get-CmdVersion 'docker' '--version'
if ($dv) {
    Write-Host ("  [OK]      {0,-10} {1}" -f 'Docker', $dv) -ForegroundColor Green
} else {
    Write-Host ("  [MISSING] {0,-10} 一键起 MySQL+Redis（最省事的方案）" -f 'Docker') -ForegroundColor Yellow
    Write-Host  "            下载: https://www.docker.com/products/docker-desktop/" -ForegroundColor DarkYellow
    $missing += @{ n='Docker Desktop'; d='https://www.docker.com/products/docker-desktop/' }
}

$pycharm = Find-Exe @(
    "D:\develop\pycharm\PyCharm *\bin\pycharm64.exe",
    "$env:LOCALAPPDATA\Programs\PyCharm*\bin\pycharm64.exe",
    "C:\Program Files\JetBrains\PyCharm*\bin\pycharm64.exe"
)
if ($pycharm) {
    $ver = $pycharm.VersionInfo.ProductVersion
    Write-Host ("  [OK]      {0,-10} {1}" -f 'PyCharm', $ver) -ForegroundColor Green
    Write-Host ("            路径: {0}" -f $pycharm.FullName) -ForegroundColor DarkGray
} else {
    Write-Host ("  [MISSING] {0,-10} 主 IDE（需专业版）" -f 'PyCharm') -ForegroundColor Yellow
    Write-Host  "            下载: https://www.jetbrains.com/pycharm/download/" -ForegroundColor DarkYellow
    $missing += @{ n='PyCharm Professional'; d='https://www.jetbrains.com/pycharm/download/' }
}

# ------------------------------------------------------------
Write-Head "P2 - 可选（加分项 / 调试便利）"

$p2 = @(
    @{ cmd='jmeter'; show='JMeter'; arg='--version'; d='https://jmeter.apache.org/download_jmeter.cgi';  note='接口压测（报告性能章节）' },
    @{ cmd='locust'; show='Locust'; arg='--version'; d='pip install locust';                             note='接口压测（Python 方案）' }
)
foreach ($t in $p2) {
    $ver = Get-CmdVersion $t.cmd $t.arg
    if ($ver) {
        Write-Host ("  [OK]      {0,-10} {1}" -f $t.show, $ver) -ForegroundColor Green
    } else {
        Write-Host ("  [MISSING] {0,-10} {1}" -f $t.show, $t.note) -ForegroundColor DarkYellow
        Write-Host ("            下载: {0}" -f $t.d) -ForegroundColor DarkGray
    }
}

# Ollama 常不在 PATH 上，优先按命令探测，失败则按安装目录兜底
$ollamaVer = Get-CmdVersion 'ollama' '--version'
if ($ollamaVer) {
    Write-Host ("  [OK]      {0,-10} {1}" -f 'Ollama', $ollamaVer) -ForegroundColor Green
} else {
    $ollamaDir = Find-Exe @("D:\develop\ollama", "$env:LOCALAPPDATA\Programs\Ollama")
    if ($ollamaDir) {
        Write-Host ("  [部分]    {0,-10} 已安装但不在 PATH，需手动启动服务" -f 'Ollama') -ForegroundColor Yellow
        Write-Host ("            位置: {0}" -f $ollamaDir.FullName) -ForegroundColor DarkGray
        Write-Host  "            启动: 进入该目录执行  .\ollama.exe serve" -ForegroundColor DarkGray
    } else {
        Write-Host ("  [MISSING] {0,-10} 本地大模型（免费离线，推荐备份方案）" -f 'Ollama') -ForegroundColor DarkYellow
        Write-Host  "            下载: https://ollama.com/download" -ForegroundColor DarkGray
    }
}

$apifox = Find-Exe @("D:\develop\apifox\Apifox.exe", "$env:LOCALAPPDATA\Programs\Apifox\Apifox.exe")
if ($apifox) {
    Write-Host ("  [OK]      {0,-10} {1}" -f 'Apifox', $apifox.VersionInfo.FileVersion) -ForegroundColor Green
} else {
    Write-Host  "  [MISSING] Apifox     API 接口测试  下载: https://apifox.com/" -ForegroundColor DarkYellow
}

# ------------------------------------------------------------
Write-Head "端口占用检测"

foreach ($item in @(
    @{p=3306;  l='MySQL'},
    @{p=6379;  l='Redis'},
    @{p=8000;  l='Django'},
    @{p=8080;  l='Vue Dev Server'},
    @{p=5173;  l='Vite 备用'},
    @{p=11434; l='Ollama'}
)) {
    $busy = $null
    try { $busy = Get-NetTCPConnection -LocalPort $item.p -State Listen -ErrorAction SilentlyContinue } catch { }
    if ($busy) {
        Write-Host ("  [占用]  {0,-6} {1}" -f $item.p, $item.l) -ForegroundColor Yellow
    } else {
        Write-Host ("  [空闲]  {0,-6} {1}" -f $item.p, $item.l) -ForegroundColor Green
    }
}

# ------------------------------------------------------------
Write-Head "Python 包可用性"

if (Get-Command python -ErrorAction SilentlyContinue) {
    foreach ($p in @('Django','rest_framework','celery','redis','pymysql','pandas','sklearn','jieba','paddle','paddlenlp','langchain','dashscope','chromadb')) {
        & python -c "import $p" 2>$null 1>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host ("  [OK]      {0}" -f $p) -ForegroundColor Green
        } else {
            Write-Host ("  [未安装]  {0}" -f $p) -ForegroundColor DarkGray
        }
    }
    Write-Host ""
    Write-Host "  安装全部后端依赖：pip install -r backend\requirements.txt" -ForegroundColor Cyan
} else {
    Write-Host "  Python 未安装，跳过。" -ForegroundColor Red
}

# ------------------------------------------------------------
Write-Head "自检结论"

if ($missing.Count -eq 0) {
    Write-Host "  所有必需组件均已就绪，可以开始部署！" -ForegroundColor Green
} else {
    Write-Host ("  共 {0} 项缺失，请按上面的下载路径安装：" -f $missing.Count) -ForegroundColor Yellow
    foreach ($m in $missing) {
        Write-Host ("    - {0,-22} {1}" -f $m.n, $m.d) -ForegroundColor White
    }
}

Write-Host ""
Write-Host "  提示：Docker Desktop 可同时替代 MySQL 与 Redis，是最省事的方案。" -ForegroundColor Cyan
Write-Host "        安装后执行：docker compose up -d" -ForegroundColor Cyan
Write-Host ""
