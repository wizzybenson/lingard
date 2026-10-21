// Lingard's reminders are local notifications, scheduled on the phone; it never receives remote pushes. expo-notifications
// still asks for the Push Notifications entitlement, which a free Apple ID (personal team) can't sign, so device
// builds failed. Dropping it changes nothing the app does. Remove this plugin if remote push is ever added.
// Listed first in app.json: file mods run in reverse order, so this one runs after expo-notifications adds the key.
const { withEntitlementsPlist } = require("expo/config-plugins");

module.exports = function withoutRemotePush(config) {
  return withEntitlementsPlist(config, (mod) => {
    delete mod.modResults["aps-environment"];
    return mod;
  });
};
