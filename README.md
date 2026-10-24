# wg-obfuscator-tuned

Проверенный вариант UDP-транспорта [ClusterM/wg-obfuscator](https://github.com/ClusterM/wg-obfuscator) для **Keenetic ARM64 Cortex-A53** и **Linux VPS x86-64**. Основан на commit `7008e0ce1ea71a39ce4b50ec9c10d2ce50e9183f`, upstream version1.6. Версия упаковки этого проекта: **0.1.0-tuned**.

Клиентская и серверная сборки используют один исходный код с разными целевыми архитектурами и конфигурациями. WireGuard, веб-панель, ключи, маршруты и назначения устройств настраиваются отдельно.

## Установка одной командой

Установщик добавляет **только отдельный UDP-транспорт** к уже настроенному WireGuard. Поддерживаются VPS Linux x86-64 с systemd и Keenetic с Entware aarch64/Cortex-A53. Запускать от root в SSH соответствующего устройства. Другие архитектуры отклоняются до установки.

Каждый экземпляр получает своё имя, бинарник, конфиг и сервис. Занятый UDP-порт и существующие файлы приводят к отказу без перезаписи. Установщик не вызывает NDM, не создаёт и не изменяет VPN-интерфейсы, политики, назначения устройств, маршруты, firewall/NAT, DNS и sysctl.

**VPS** — `127.0.0.1:51820` заменить на endpoint нужного существующего WireGuard. Здесь выбран внешний UDP-порт `24443`:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && curl -fsSL --proto '=https' --proto-redir '=https' https://raw.githubusercontent.com/Bober-Den/wg-obfuscator-tuned/main/install.sh -o "$f" && sh "$f" vps --name main --target 127.0.0.1:51820 --listen-port 24443)
```

Ключ транспорта генерируется на VPS и сохраняется в `/usr/local/lib/wgot/main/shared-key.txt` с правами `600`; в вывод он не попадает. Этот же ключ нужен на Keenetic. Передать его отдельно защищённым способом; это не приватный ключ WireGuard.

**Keenetic, Entware SSH** — документационный адрес `198.51.100.10` заменить на IPv4 своего VPS. Установщик скрыто запросит тот же ключ; для автоматического запуска можно добавить `--key-file /opt/etc/wgot-shared.key` с заранее переданным файлом:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && curl -fsSL --proto '=https' --proto-redir '=https' https://raw.githubusercontent.com/Bober-Den/wg-obfuscator-tuned/main/install.sh -o "$f" && sh "$f" keenetic --name main --target 198.51.100.10:24443 --listen-port 13365)
```

Keenetic слушает только `127.0.0.1:13365`. Подключение WireGuard к этому endpoint выполняется отдельно вручную: установщик не переключает действующие VPN. При создании нового подключения оставить его без назначения устройств. На VPS доступ к выбранному UDP-порту нужно разрешить отдельно в используемом firewall, если он закрыт.

### Приватный репозиторий

Публичные команды выше работают только с публичным репозиторием. Для приватного репозитория требуется заранее экспортированный `GITHUB_TOKEN` с правом чтения Contents этого репозитория. Токен не вставлять в команду или URL; следующие команды передают его curl через stdin, а установщик — через временный файл с правами `600`.

VPS:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && printf 'header = "Authorization: Bearer %s"\n' "${GITHUB_TOKEN:?Export a read-only GITHUB_TOKEN first}" | curl --config - -fsSL --proto '=https' --proto-redir '=https' -H 'Accept: application/vnd.github.raw+json' 'https://api.github.com/repos/Bober-Den/wg-obfuscator-tuned/contents/install.sh?ref=main' -o "$f" && sh "$f" vps --name main --target 127.0.0.1:51820 --listen-port 24443)
```

Keenetic:

```sh
(umask 077; f=$(mktemp) && trap 'rm -f "$f"' 0 && printf 'header = "Authorization: Bearer %s"\n' "${GITHUB_TOKEN:?Export a read-only GITHUB_TOKEN first}" | curl --config - -fsSL --proto '=https' --proto-redir '=https' -H 'Accept: application/vnd.github.raw+json' 'https://api.github.com/repos/Bober-Den/wg-obfuscator-tuned/contents/install.sh?ref=main' -o "$f" && sh "$f" keenetic --name main --target 198.51.100.10:24443 --listen-port 13365)
```

Из уже скачанной копии репозитория интернет и GitHub-токен не нужны:

```sh
sh install.sh vps --source-dir . --target 127.0.0.1:51820 --listen-port 24443
sh install.sh keenetic --source-dir . --target 198.51.100.10:24443 --listen-port 13365 --key-file /opt/etc/wgot-shared.key
```

Это команды для разных устройств. Параметры `--dry-run` (план без записи и загрузок), `--no-start` (установка без запуска и автозапуска), `--listen-port auto` (свободный порт из `24000–24999`) и `--name second` описаны в [инструкции по установке и откату](docs/INSTALL.md). Бинарники проверяются по встроенным SHA256 и скачиваются с закреплённого commit, а не из изменяемого `main`. Для закрепления самого установщика заменить `main` в URL на проверенный commit.

## Изменения

- До32 пакетов обрабатывается за событие готовности сокета, затем цикл обслуживает другие события/таймеры.
- Для UDP-сокетов процесса запрашивается receive buffer1 МиБ и send buffer512 КиБ. Фактический размер зависит от системных пределов; в проверенной Linux-конфигурации наблюдалось2 МиБ/1 МиБ.
- ARM64-сборка: `-O3 -mcpu=cortex-a53`; серверная: `-O3 -mtune=generic`. Обе статические.
- Формат обфускации, кодек и шифрование WireGuard не менялись. Проверялись AUTO/STUN и реальная передача HTTPS/iperf в исходном развёртывании.

Это самостоятельный вариант транспорта, с сохранением авторства upstream. PCA/Phobos-панель и расширения Phobos MEDIA/TLS/SOCKS5 в этот репозиторий не входят; для таких расширений нужна совместимая сборка соответствующего проекта.

## Готовые проверенные сборки

| Назначение | Файл |
| --- | --- |
| Keenetic Entware, aarch64/Cortex-A53 | [prebuilt/keenetic-arm64/wgot-client](prebuilt/keenetic-arm64/wgot-client) |
| Linux VPS, x86-64 | [prebuilt/linux-x86_64/wgot-server](prebuilt/linux-x86_64/wgot-server) |

Это сохранённые бинарники, прошедшие прежние аппаратные проверки, а не новые бинарники CI. Полный соответствующий исходный код включён в `src/`. Архитектуру нужно проверить через `uname -m` до запуска. Для других Keenetic CPU эта ARM64-сборка не подходит автоматически.

Из корня репозитория на Linux:

```sh
sha256sum -c prebuilt/SHA256SUMS
chmod +x prebuilt/linux-x86_64/wgot-server
prebuilt/linux-x86_64/wgot-server --help
```

На Keenetic проверяется соответствующий ARM64-файл. Установщик копирует бинарник под отдельным именем для каждого экземпляра: `wgotc-ИМЯ` / `wgots-ИМЯ`, чтобы разделить его с другими обфускаторами.

## Сборка и тесты

Linux x86-64, GCC/make/Python3; для ARM64 дополнительно нужны `gcc-aarch64-linux-gnu` и `libc6-dev-arm64-cross`.

```sh
bash scripts/build.sh all
bash scripts/test.sh
python3 tests/udp_roundtrip.py --binary dist/linux-x86_64/wgot-server
```

В GitHub Actions выполняются обе сборки, проверка CRC-кодека с ASan/UBSan, loopback-тесты AUTO/STUN и ARM64 smoke-тест под QEMU. Скачиваемые результаты помещаются в Actions artifacts. Workflow запускается при push/PR и вручную; секреты и доступ к рабочим серверам ему не нужны. Получившиеся в CI хеши могут отличаться от сохранённых prebuilt из-за версии компилятора — это отдельные сборки, требующие проверки перед заменой на устройстве.

## Документация

- [Развёртывание и безопасный откат](docs/DEPLOYMENT.md).
- [Параметры установщика, проверка и удаление отдельного экземпляра](docs/INSTALL.md).
- [Измеренные эффекты и ограничения](docs/VALIDATION.md).
- [Происхождение исходников и сборок](SOURCE-PROVENANCE.json).
- [Изменения](CHANGELOG.md), [авторство и сторонние компоненты](THIRD-PARTY-NOTICES.md).

В репозитории только исходники, шаблоны и артефакты. Рабочие адреса, пользовательские конфиги, ключи, пароли и токены не включены.
