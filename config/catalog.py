import json
from config.settings import ROOT


def projects():
    return json.loads((ROOT / 'project_rules/rules.json').read_text('utf-8'))


def profiles():
    return json.loads((ROOT / 'lawfirm_profiles/profiles.json').read_text('utf-8'))


def project_by_id(key):
    return next((p for p in projects() if p['id'] == key), None)


def profile_by_id(key):
    return next((p for p in profiles() if p['id'] == key), None)
