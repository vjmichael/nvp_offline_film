// Keep the selected Take and its spatial listener in one state transition.
// The native desktop bridge remains the sole source/approval authority.
export function selectTake(takes, takeId) {
  const item = takes.find(take => take.take_id === takeId);
  const listeners = Array.isArray(item?.listeners) ? item.listeners : [];
  return {takeId:item?.take_id || '',listener:listeners.find(p => typeof p==='string' && p.length>0) || ''};
}

export function loadInventory(takes, projectId, bridge, revision) {
  return {takes,projectId,bridge,revision,...selectTake(takes,takes[0]?.take_id)};
}

export function chooseTake(inventory,takeId) {
  return {...inventory,...selectTake(inventory.takes,takeId)};
}

export function chooseListener(inventory,listener) {
  const item=inventory.takes.find(take=>take.take_id===inventory.takeId);
  const valid=typeof listener==='string' && listener.length>0 &&
    Array.isArray(item?.listeners) && item.listeners.includes(listener);
  return {...inventory,listener:valid?listener:''};
}

export function currentInventory(inventory,projectId,bridge,revision) {
  return inventory.projectId===projectId && inventory.bridge===bridge && inventory.revision===revision
    ?inventory:loadInventory([],projectId,bridge,revision);
}
