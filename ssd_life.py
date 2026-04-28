#!/usr/bin/env python3
"""
SSD Life Monitor - ФИНАЛЬНАЯ ВЕРСИЯ
Правильно парсит TBW из вывода nvme smart-log
"""

import subprocess
import re

class SSDMonitor:
    def __init__(self):
        self.has_nvme_cli = self._check_nvme_cli()
        self.has_smartctl = self._check_smartctl()

    def _check_nvme_cli(self):
        try:
            subprocess.run(['nvme', 'version'], capture_output=True, check=True)
            return True
        except:
            return False

    def _check_smartctl(self):
        try:
            subprocess.run(['smartctl', '--version'], capture_output=True, check=True)
            return True
        except:
            return False

    def find_all_ssd(self):
        ssd_disks = []

        if self.has_nvme_cli:
            try:
                result = subprocess.run(['sudo', 'nvme', 'list'], capture_output=True, text=True)
                for line in result.stdout.split('\n'):
                    if '/dev/nvme' in line:
                        parts = line.split()
                        if len(parts) >= 1:
                            ssd_disks.append({
                                'device': parts[0],
                                'model': parts[1] if len(parts) > 1 else 'Unknown',
                                'type': 'nvme'
                            })
            except:
                pass

        if self.has_smartctl:
            try:
                result = subprocess.run(['lsblk', '-d', '-o', 'NAME,TYPE,ROTA', '-n'],
                                       capture_output=True, text=True)
                for line in result.stdout.strip().split('\n'):
                    if not line:
                        continue
                    parts = line.split()
                    if len(parts) >= 3:
                        name = parts[0]
                        type_ = parts[1]
                        rota = parts[2]

                        if type_ not in ['rom', 'loop'] and rota == '0':
                            device = f"/dev/{name}"
                            if not any(d['device'] == device for d in ssd_disks):
                                ssd_disks.append({
                                    'device': device,
                                    'model': 'SATA SSD',
                                    'type': 'sata'
                                })
            except:
                pass

        return ssd_disks

    def get_nvme_stats(self, device):
        """Получает статистику для NVMe диска (правильный парсинг)"""
        try:
            result = subprocess.run(['sudo', 'nvme', 'smart-log', device],
                                   capture_output=True, text=True)
            output = result.stdout

            stats = {}

            # Процент использования
            match = re.search(r'percentage_used\s*:\s*(\d+)%', output)
            if match:
                used = int(match.group(1))
                stats['life_percent'] = 100 - used
            else:
                stats['life_percent'] = None

            # TBW - берем число из скобок (уже в TB)
            match = re.search(r'Data Units Written\s*:\s*\d+\s*\(([\d.]+)\s*TB\)', output)
            if match:
                stats['tb_written'] = float(match.group(1))
            else:
                # Если не нашли в скобках, пробуем старый способ
                match = re.search(r'data_units_written\s*:\s*(\d+)', output)
                if match:
                    data_units = int(match.group(1))
                    stats['tb_written'] = (data_units * 512000) / (1024**4)
                else:
                    stats['tb_written'] = None

            # TBR
            match = re.search(r'Data Units Read\s*:\s*\d+\s*\(([\d.]+)\s*TB\)', output)
            if match:
                stats['tb_read'] = float(match.group(1))
            else:
                match = re.search(r'data_units_read\s*:\s*(\d+)', output)
                if match:
                    data_units = int(match.group(1))
                    stats['tb_read'] = (data_units * 512000) / (1024**4)
                else:
                    stats['tb_read'] = None

            # Температура (берем первую температуру, которая не в Кельвинах)
            temp = None
            # Сначала пробуем Temperature Sensor 1
            match = re.search(r'Temperature Sensor 1\s*:\s*(\d+)\s*°C', output)
            if match:
                temp = int(match.group(1))
            else:
                # Пробуем composite_temperature
                match = re.search(r'composite_temperature\s*:\s*(\d+)', output)
                if match:
                    raw_temp = int(match.group(1))
                    if raw_temp > 100:
                        temp = raw_temp - 273
                    else:
                        temp = raw_temp

            if temp is None:
                match = re.search(r'temperature\s*:\s*(\d+)\s*°C', output)
                if match:
                    temp = int(match.group(1))

            stats['temperature'] = temp if temp and 0 < temp < 100 else None

            # Время работы
            match = re.search(r'power_on_hours\s*:\s*(\d+)', output)
            stats['power_on_hours'] = int(match.group(1)) if match else None

            # Аварийные выключения
            match = re.search(r'unsafe_shutdowns\s*:\s*(\d+)', output)
            stats['unsafe_shutdowns'] = int(match.group(1)) if match else None

            return stats

        except Exception as e:
            print(f"Ошибка: {e}")
            return {
                'life_percent': None,
                'tb_written': None,
                'tb_read': None,
                'temperature': None,
                'power_on_hours': None,
                'unsafe_shutdowns': None
            }

    def get_sata_stats(self, device):
        """Получает статистику для SATA SSD"""
        try:
            result = subprocess.run(['sudo', 'smartctl', '-a', device],
                                   capture_output=True, text=True)
            output = result.stdout + result.stderr

            stats = {}

            # Процент жизни
            match = re.search(r"Media_Wearout_Indicator\s+0x[\da-f]+\s+(\d+)", output)
            if match:
                value = int(match.group(1))
                if value <= 100:
                    stats['life_percent'] = value
                elif value < 200:
                    stats['life_percent'] = 200 - value
                else:
                    stats['life_percent'] = None
            else:
                match = re.search(r"Wear_Leveling_Count\s+0x[\da-f]+\s+(\d+)", output)
                if match:
                    value = int(match.group(1))
                    stats['life_percent'] = value if value <= 100 else None
                else:
                    stats['life_percent'] = None

            # TBW
            match = re.search(r"Total_LBA_Written\s+0x[\da-f]+\s+(\d+)", output)
            if match:
                lba = int(match.group(1))
                stats['tb_written'] = (lba * 512) / (1024**4)
            else:
                match = re.search(r"Total LBAs Written:\s*(\d+)", output)
                if match:
                    lba = int(match.group(1))
                    stats['tb_written'] = (lba * 512) / (1024**4)
                else:
                    stats['tb_written'] = None

            # TBR
            match = re.search(r"Total_LBA_Read\s+0x[\da-f]+\s+(\d+)", output)
            if match:
                lba = int(match.group(1))
                stats['tb_read'] = (lba * 512) / (1024**4)
            else:
                match = re.search(r"Total LBAs Read:\s*(\d+)", output)
                if match:
                    lba = int(match.group(1))
                    stats['tb_read'] = (lba * 512) / (1024**4)
                else:
                    stats['tb_read'] = None

            # Температура
            temp = None
            patterns = [
                r"Temperature:\s*(\d+)",
                r"Current Drive Temperature:\s*(\d+)",
                r"Temperature Celsius:\s*(\d+)"
            ]
            for pattern in patterns:
                match = re.search(pattern, output)
                if match:
                    raw_temp = int(match.group(1))
                    if 0 <= raw_temp <= 100:
                        temp = raw_temp
                        break
            stats['temperature'] = temp
            stats['power_on_hours'] = None
            stats['unsafe_shutdowns'] = None

            return stats

        except Exception as e:
            return {
                'life_percent': None,
                'tb_written': None,
                'tb_read': None,
                'temperature': None,
                'power_on_hours': None,
                'unsafe_shutdowns': None
            }

    def format_size(self, tb):
        if tb is None:
            return "N/A"
        if tb < 0.001:
            return f"{tb * 1024:.2f} GB"
        return f"{tb:.2f} TB"

    def print_stats(self, disk):
        print("\n" + "=" * 60)
        print(f"💾 {disk['device']}")
        print(f"   Модель: {disk['model']}")
        print(f"   Тип: {disk['type'].upper()}")
        print("-" * 60)

        stats = disk.get('stats', {})

        # Процент жизни
        life = stats.get('life_percent')
        if life is not None:
            if life >= 80:
                status = "✓ Отлично"
            elif life >= 50:
                status = "⚠️ Хорошо"
            elif life >= 20:
                status = "⚠️ Износ заметен"
            else:
                status = "🔴 КРИТИЧЕСКИЙ!"

            print(f"   💚 Оставшийся ресурс: {life}%  {status}")
        else:
            print("   💚 Оставшийся ресурс: не определен")

        # TBW
        tbw = stats.get('tb_written')
        if tbw is not None:
            print(f"   📝 Всего записано: {self.format_size(tbw)}")
        else:
            print("   📝 Всего записано: не определено")

        # TBR
        tbr = stats.get('tb_read')
        if tbr is not None:
            print(f"   📖 Всего прочитано: {self.format_size(tbr)}")

        # Температура
        temp = stats.get('temperature')
        if temp is not None:
            if temp < 45:
                temp_status = "✓ Отлично"
            elif temp < 55:
                temp_status = "⚠️ Нормально"
            elif temp < 65:
                temp_status = "⚠️ Повышена"
            else:
                temp_status = "🔴 Критическая!"
            print(f"   🌡️  Температура: {temp}°C  {temp_status}")
        else:
            print("   🌡️  Температура: не определена")

        # Дополнительно для NVMe
        if disk['type'] == 'nvme':
            hours = stats.get('power_on_hours')
            if hours and hours > 0:
                days = hours // 24
                print(f"   ⏱️  Время работы: {days} дней ({hours} часов)")

            shutdowns = stats.get('unsafe_shutdowns')
            if shutdowns and shutdowns > 0:
                print(f"   ⚠️  Аварийных выключений: {shutdowns}")

    def run(self):
        print("\n" + "═" * 60)
        print("🔍 SSD LIFE MONITOR")
        print("═" * 60)

        if not self.has_nvme_cli and not self.has_smartctl:
            print("\n❌ Ошибка: Установите nvme-cli или smartmontools")
            print("   sudo apt install nvme-cli smartmontools")
            return

        print("\n📋 Поиск SSD дисков...")
        disks = self.find_all_ssd()

        if not disks:
            print("❌ SSD диски не найдены!")
            return

        print(f"✅ Найдено SSD: {len(disks)}")

        for disk in disks:
            if disk['type'] == 'nvme':
                stats = self.get_nvme_stats(disk['device'])
            else:
                stats = self.get_sata_stats(disk['device'])

            disk['stats'] = stats
            self.print_stats(disk)

        print("\n" + "═" * 60 + "\n")

def main():
    monitor = SSDMonitor()
    monitor.run()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Программа прервана")
    except Exception as e:
        print(f"\n❌ Ошибка: {e}")
        print("\nПопробуйте запустить с sudo: sudo python3 ssd_life.py")

if __name__ == "__main__":
    main()
