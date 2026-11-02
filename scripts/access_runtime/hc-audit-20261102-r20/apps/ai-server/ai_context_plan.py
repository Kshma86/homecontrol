"""Select HC data before building a context; no database or provider I/O."""
def context_sections(message, history=(), *, images=False):
    if images:
        return []
    text = str(message or '').lower()
    domains = {
        'irrigation': ('öntöz', 'ontoz', 'locsol', 'irrigation', 'szelep', 'pumpa', 'pilot', 'navigator', 'csepegtet', 'csöpög', 'csopog'),
        'climate': ('klím', 'klim', 'gree', 'climate'),
        'robot': ('x10', 'xiaomi', 'robot', 'porszív', 'porsziv', 'vacuum', 'térkép', 'terkep'),
        'solar': ('napelem', 'solar', 'growatt', 'inverter', 'termelés', 'termeles'),
        'power_wall': ('power wall', 'power-wall', 'konnektor', 'aljzat', 'plug'),
        'server_power': ('hc szerver', 'homecontrol szerver', 'server_power'),
        'backup': ('mentés', 'mentes', 'backup', 'visszaáll', 'visszaall'),
        'notes': ('jegyzet', 'notes'),
        'weather': ('időjár', 'idojar', 'weather', 'eső', 'eso', 'csapad'),
        'home_statistics': ('páratart', 'paratart', 'hőmér', 'homer', 'humidity', 'temperature', 'moisture', 'talajnedv', 'hc stats', 'home statistics'),
        'scheduler_ai': ('scheduler', 'időzít', 'idozit', 'ütemez', 'utemez', 'schedule'),
        'performance': ('performance', 'rendszerterhel', 'cpu', 'memória', 'memoria'),
        'ai_chat_audit': ('ai audit', 'chat audit', 'ai kérés', 'ai keres', 'ai kérések', 'ai keresek'),
    }
    def selected(value):
        return [name for name, words in domains.items() if any(word in value for word in words)]
    result = selected(text)
    # A named current domain wins over older, unrelated conversation topics.
    if not result and any(word in text for word in ('és', 'annak', 'mennyi', 'mikor', 'beállít', 'beallit', 'általában', 'altalaban', 'az ', 'ez ')):
        for turn in reversed(list(history or [])[-4:]):
            if isinstance(turn, dict):
                if turn.get('role') == 'assistant':
                    continue
                prior = str(turn.get('content') or turn.get('message') or '').lower()
            else:
                prior = str(turn).lower()
            result = selected(prior)
            if result:
                text += '\n' + prior
                break
    if any(word in text for word in ('minden modul', 'teljes rendszer', 'hc rendszer', 'összes modul', 'osszes modul')):
        result.extend(('irrigation', 'climate', 'robot', 'solar', 'power_wall', 'scheduler_ai'))
    if 'climate' in result:
        result = [name for name in result if name != 'home_statistics']
        if any(word in text for word in ('fogyaszt', 'watt', 'kwh', 'energia', 'áram', 'aram', 'teljesítmény', 'teljesitmeny')):
            result.remove('climate')
            result.append('climate_power_history')
        elif any(word in text for word in ('beállít', 'beallit', 'paraméter', 'parameter', 'mód', 'mod', 'fan', 'célhő', 'celho', 'általában', 'altalaban')):
            result.extend(('climate_history', 'climate_schedules'))
    if 'irrigation' in result:
        if any(word in text for word in ('mikor', 'ma', 'tegnap', 'ciklus', 'hány', 'hany', 'perc', 'lista', 'sorold', 'indult', 'leáll', 'leall')):
            result.append('irrigation_statistics')
        if any(word in text for word in ('pilot', 'navigator', 'miért', 'miert', 'talaj')):
            result.extend(('irrigation_pilot', 'weather'))
    if any(word in text for word in ('moisture', 'talajnedv', 'nedvesség', 'nedvesseg')):
        result = [name for name in result if name != 'home_statistics']
        result.extend(('irrigation', 'irrigation_statistics'))
    if 'server_power' in result:
        result = [name for name in result if name != 'power_wall']
    return list(dict.fromkeys(result))
