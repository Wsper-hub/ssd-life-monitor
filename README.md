# SSD Life Monitor

Программа для мониторинга ресурса NVMe и SATA SSD дисков. Показывает:
- 💚 Оставшийся ресурс в процентах
- 📝 Всего записано (TBW)
- 📖 Всего прочитано (TBR)
- 🌡️ Температура
- ⏱️ Время работы и аварийные выключения (для NVMe)

## Установка

### Зависимости
```bash
sudo apt install nvme-cli smartmontools
# ssd-life-monitor

## Запуск

ssd-life
