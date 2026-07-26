#!/bin/bash
# AI 情报雷达 - Linux 服务器一键定时部署脚本
# 用法: 把本脚本和 ai_radar.py 放在同一目录,执行:  bash setup_linux.sh
# 效果: 注册 crontab 定时任务,每天"北京时间 08:00"自动运行(自动换算服务器时区)
# 重复执行本脚本是安全的,会覆盖旧的雷达任务而不会重复添加。

set -e
RADAR_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"
MARK="# ai-radar-daily"

if [ -z "$PY" ]; then
  echo "未找到 python3,请先安装: sudo apt install -y python3  (Debian/Ubuntu)"
  echo "                        sudo yum install -y python3  (CentOS)"
  exit 1
fi
if [ ! -f "$RADAR_DIR/ai_radar.py" ]; then
  echo "本脚本必须和 ai_radar.py 放在同一目录里再运行"
  exit 1
fi

# 自检
echo "== 先跑一次离线自检 =="
"$PY" "$RADAR_DIR/ai_radar.py" --demo

# 把"北京时间 08:00"换算成服务器本地时间
read -r HOUR MIN <<< "$("$PY" - <<'EOF'
from datetime import datetime, timedelta, timezone
cst = timezone(timedelta(hours=8))
beijing_8am = datetime.now(cst).replace(hour=8, minute=0, second=0, microsecond=0)
local = beijing_8am.astimezone()  # 服务器本地时区
print(local.hour, local.minute)
EOF
)"

# 若存在 .env 则在运行前加载(用于 Telegram/Server酱 推送密钥)
CMD="cd $RADAR_DIR && ([ -f .env ] && . ./.env; $PY ai_radar.py >> radar.log 2>&1)"
LINE="$MIN $HOUR * * * $CMD $MARK"

# 写入 crontab(去掉旧的同名任务再追加)
( crontab -l 2>/dev/null | grep -v "$MARK" ; echo "$LINE" ) | crontab -

echo ""
echo "✅ 部署完成!"
echo "   程序目录 : $RADAR_DIR"
echo "   服务器时区: $(date +%Z%z)"
echo "   定时计划 : 服务器本地 $HOUR:$(printf '%02d' "$MIN") = 北京时间 08:00,每天一次"
echo "   简报输出 : $RADAR_DIR/reports/"
echo "   运行日志 : $RADAR_DIR/radar.log"
echo ""
echo "常用命令:"
echo "   立即手动跑一次 : cd $RADAR_DIR && python3 ai_radar.py"
echo "   查看定时任务   : crontab -l"
echo "   卸载定时任务   : crontab -l | grep -v '$MARK' | crontab -"
echo ""
echo "配置手机推送(可选): 在 $RADAR_DIR 下创建 .env 文件,内容示例:"
echo '   export TELEGRAM_BOT_TOKEN="123:abc"'
echo '   export TELEGRAM_CHAT_ID="456789"'
echo '   export SERVERCHAN_KEY="SCTxxxx"'
