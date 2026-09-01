# Raspberry Pi 自動水やりシステム

Raspberry Piを使って、鉢植えのミントに自動で水を与えるシステムを構築します。

## システム構成

システムにはRaspberry Pi 3B+とUSBポンプ、Tapo P105スマートプラグを使用します。

水は20Lのタンクから供給し、内径5mmのホースを使用します。

### 使用する機器

| 機器 | 型番 | 用途 |
|---|---|---|
| Raspberry Pi | 3B+ | 制御用コンピューター |
| スマートプラグ | P105 | ポンプの電源制御 |
| USBポンプ | USB-5V-PUMP | 水の供給 |
| ホース | INNER-5MM | 給水用 |

## 水やりの設定

通常は毎日18:00に水やりを実行します。

1回あたり約500mlの水を与えます。

5泊6日の旅行では、最低でも3L程度の水が必要です。
余裕を考えて20Lのタンクを使用します。

### systemd timer

Linuxのsystemd timerを使用して、毎日18:00に水やりプログラムを実行します。

```ini
[Unit]
Description=Watering Timer

[Timer]
OnCalendar=*-*-* 18:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

`Persistent=true`を設定すると、指定時刻にシステムが停止していた場合でも、次回起動時にタイマーイベントを処理できます。

### systemdの確認

登録されているタイマーは以下のコマンドで確認できます。

```bash
systemctl --user list-timers
```

サービスの状態を確認する場合は、

```bash
systemctl --user status watering.service
```

を実行します。

## Raspberry Piの温度確認

Raspberry Piでは、以下のコマンドでCPU温度を確認できます。

```bash
vcgencmd measure_temp
```

実行結果の例：

```text
temp=48.2'C
```

CPU温度が70℃を超える場合は、冷却について検討します。

## Tapo P105

Tapo P105はLAN経由で制御できます。

Raspberry PiからIPアドレス`192.168.0.25`のP105を操作します。

Pythonから制御する場合は、`kasa`ライブラリを利用できます。

```bash
python3 -m pip install python-kasa
```

デバイスの状態を確認する例：

```bash
kasa --host 192.168.0.25
```

公式サイト：

https://www.tp-link.com/jp/home-networking/smart-plug/tapo-p105/

## トラブルシューティング

### systemdサービスが実行されない

以下のコマンドでログを確認します。

```bash
journalctl --user -u watering.service
```

`Exec format error`が表示された場合、スクリプトの先頭に正しいshebangがあるか確認します。

例えばPythonスクリプトなら、

```python
#!/usr/bin/env python3
```

を先頭に記述します。

### ポンプが動作しない

まずUSBポンプに5Vの電源が供給されているか確認します。

LANケーブルを5V電源ケーブルとして使用する場合は、使用する芯線と電流容量を確認してください。

## 注意事項

水を扱うため、Raspberry Pi本体やUSB電源部分に水がかからないようにします。

屋外で使用する場合は、防水ケースや防水コネクタを使用してください。