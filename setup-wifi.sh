#!/usr/bin/env bash

echo "按音箱顶部按钮6秒进入配网模式，小讯会开启热点"
echo "请连接小讯的 WiFi 热点后运行此脚本"
echo ""

read -r -p "WiFi 名称 (SSID): " ssid
read -r -s -p "WiFi 密码:     " password
echo ""

echo "正在配置 WiFi 网络..."
curl 'http://192.168.43.1:8989/api/configwifi' \
  --data-raw "{\"ssid\":\"$ssid\",\"secure\":\"WPA\",\"password\":\"$password\"}"
