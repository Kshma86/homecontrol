export function selectedDocumentationModule(docs, selectedKey) {
  const modules = docs?.modules || [];
  const selected = modules.find((item) => item.key === selectedKey) || modules[0] || {};
  return {
    modules,
    selected,
    source: selected.source || {},
    bindings: selected.bindings || [],
    devices: selected.devices || [],
    buttons: selected.buttons || [],
    deepDive: selected.deep_dive || [],
  };
}

export function aboutViewModel(about) {
  const source = about?.source || {};
  const totals = source.totals || {};
  const inventory = about?.inventory || {};
  const devices = inventory.devices || {};
  const entities = inventory.entities || {};
  const docker = about?.docker || {};
  const dockerSummary = docker.summary || {};
  const modules = source.modules || [];
  const sensorTypes = inventory.sensor_types || [];
  const metricTypes = inventory.metric_types || [];
  const containers = docker.containers || [];
  const server = about?.server || {};
  const cpu = server.cpu || {};
  const memory = server.memory || {};
  const diskRoot = server.disk?.root || {};
  const database = about?.database || {};
  const relationSummary = database.relation_summary || {};
  const measurement = database.measurement || {};
  const dbConnections = database.connections || {};
  const topTables = database.top_tables || [];
  const metricActivity = database.metric_activity_24h || [];
  const schemaTables = database.schema_tables || [];

  return {
    source,
    totals,
    inventory,
    devices,
    entities,
    docker,
    dockerSummary,
    modules,
    sensorTypes,
    metricTypes,
    containers,
    server,
    cpu,
    memory,
    diskRoot,
    database,
    relationSummary,
    measurement,
    dbConnections,
    topTables,
    metricActivity,
    schemaTables,
  };
}
