"""Restricted r2 rollback entrypoint for the additive r4 DB; use only in its frozen image."""
import importlib
from flask import jsonify,request
import app as hc
from startup_schema_contract import check_domain
from runtime_schema_contract import check_runtime_schema


def domain_check(domain):
    def check(self): check_domain(hc.fetch_one,domain)
    return check


def runtime_check(domain):
    def check(self):
        execute=getattr(self,'execute_sql',None) or self.execute_one
        check_runtime_schema(execute,domain)
    return check


# Keep the old feature implementation while using read-only checks against the
# explicitly migrated schema. Never restore startup DDL/seeds or admin runtime.
for module,class_name,method,domain in (
    ('schema_service','HcSchemaService','ensure_pilot_schema','pilot'),
    ('scheduler_service','SchedulerService','ensure_scheduler_schema','scheduler'),
    ('season_profile_service','SeasonProfileService','ensure_schema','season'),
    ('admin_service','AdminService','ensure_notes_schema','notes')):
    setattr(getattr(importlib.import_module(module),class_name),method,domain_check(domain))
for module,class_name,method,domain in (
    ('schema_service','HcSchemaService','ensure_power_wall_schema','power_wall'),
    ('process_binding_service','ProcessBindingService','ensure_schema','bindings'),
    ('irrigation_service','IrrigationService','ensure_summary_schema','summaries'),
    ('admin_service','AdminService','ensure_opening_schema','opening'),
    ('admin_service','AdminService','ensure_temperature_schema','temperature'),
    ('ai_chat_audit_service','AiChatAuditService','ensure_schema','ai_audit'),
    ('page_usage_service','PageUsageService','ensure_schema','page_usage'),
    ('mower_parameters_store','MowerParametersStore','ensure_schema','mower_parameters'),
    ('mower_firmware_store','MowerFirmwareStore','ensure_schema','mower_staging'),
    ('mower_firmware_sessions_store','MowerFirmwareSessionsStore','ensure_schema','mower_sessions'),
    ('mower_firmware_operations_store','MowerFirmwareOperationsStore','ensure_schema','mower_operations')):
    setattr(getattr(importlib.import_module(module),class_name),method,runtime_check(domain))
from climate_window_guard import ClimateWindowGuard
old_config=ClimateWindowGuard.config
def window_config(self):
    check_runtime_schema(self.execute_one,'climate_window')
    self.ready=True
    return old_config(self)
ClimateWindowGuard.config=window_config

app=hc.app
@app.before_request
def restrict_rollback_mutations():
    path=request.path
    if path.startswith('/api/sql-lab/') or (request.method not in ('GET','HEAD','OPTIONS') and
            (path.startswith('/api/backup') or path.startswith('/api/ai/node/'))):
        return jsonify(ok=False,error='Restricted rollback: SQL Lab, backup mutations and AI power commands are temporarily unavailable'),503

hc.get_startup_service().start_application()
hc.get_context_service().snapshot(sections=hc.DEFAULT_CONTEXT_SECTIONS)
