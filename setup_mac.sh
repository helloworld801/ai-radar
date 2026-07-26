#!/bin/bash
# AI 情报雷达 - Mac 一键定时部署脚本
# 用法: 把本脚本和 ai_radar.py 放在同一文件夹,然后执行:  bash setup_mac.sh
# 效果: 注册 launchd 定时任务,每天 08:00 自动运行雷达(睡眠错过会在唤醒后补跑)

set -e
RADAR_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3)"

if [ -z "$PY" ]; then
  echo "未找到 python3,请先安装: xcode-select --install  或  brew install python3"
  exit 1
fi
if [ ! -f "$RADAR_DIR/ai_radar.py" ]; then
  echo "本脚本必须和 ai_radar.py 放在同一文件夹里再运行"
  exit 1
fi

PLIST="$HOME/Library/LaunchAgents/com.ai-radar.daily.plist"
mkdir -p "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.ai-radar.daily</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$RADAR_DIR/ai_radar.py</string>
    </array>
    <key>WorkingDirectory</key><string>$RADAR_DIR</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>8</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key><string>$RADAR_DIR/radar.log</string>
    <key>StandardErrorPath</key><string>$RADAR_DIR/radar.log</string>
    <!-- 如需 Telegram/Server酱 推送,取消下面注释并填入你的密钥
    <key>EnvironmentVariables</key>
    <dict>
        <key>TELEGRAM_BOT_TOKEN</key><string>你的token</string>
        <key>TELEGRAM_CHAT_ID</key><string>你的chat_id</string>
        <key>SERVERCHAN_KEY</key><string>你的sendkey</string>
    </dict>
    -->
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "✅ 部署完成!"
echo "   程序目录 : $RADAR_DIR"
echo "   定时计划 : 每天 08:00 自动运行(睡眠错过会在唤醒后补跑)"
echo "   简报输出 : $RADAR_DIR/reports/"
echo "   运行日志 : $RADAR_DIR/radar.log"
echo ""
echo "常用命令:"
echo "   立即手动跑一次 : python3 $RADAR_DIR/ai_radar.py"
echo "   立即触发定时任务: launchctl start com.ai-radar.daily"
echo "   卸载定时任务   : launchctl unload $PLIST"
