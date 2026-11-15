local health = { status = "Progressing", message = "Waiting for the child Application" }
if obj.status ~= nil then
  if obj.status.health ~= nil and obj.status.health.status == "Degraded" then
    return obj.status.health
  end
  if obj.status.operationState ~= nil and obj.status.operationState.phase == "Running" then
    health.message = "Child Application is syncing"
    return health
  end
  if obj.status.operationState ~= nil and (obj.status.operationState.phase == "Failed" or obj.status.operationState.phase == "Error") then
    return { status = "Degraded", message = obj.status.operationState.message or "Child Application sync failed" }
  end
  if obj.status.sync ~= nil and obj.status.sync.status == "Synced" and obj.status.health ~= nil then
    return obj.status.health
  end
end
return health
