import { B as r } from "./DataManagement-CjZmo8Br.js";
import { _ as p, l as a, k as d, e as m, m as u, q as s, A as l, x as n } from "./vendor-JxinjXxC.js";
import "./vendor-fortawesome-DD1DIYBi.js";
import "./index-BRkE2tw3.js";
import "./vendor-bootstrap-BTTEOGLM.js";
import "./vendor-jquery-CEMonh9Y.js";
import "./vendor-axios-CL9DOa3h.js";
import "./dynamic-import-helper-BheWnx7M.js";

const b = { name: "BackupCloudSeafile", mixins: [r] };
const c = { class: "backup-cloud-seafile" };

function f(n, e, k, g, C, w) {
  const t = a("openwb-base-text-input");
  const i = a("openwb-base-number-input");
  return d(), m("div", c, [
    u(t, {
      title: "Cloud-URL",
      subtype: "url",
      required: "",
      "model-value": n.backupCloud.configuration.ip_address,
      "onUpdate:modelValue": e[0] || (e[0] = (o) => n.updateConfiguration(o, "configuration.ip_address")),
    }, {
      help: s(() => e[6] || (e[6] = [l(" Die Cloud-URL wird als Basis-URL des Seafile-Servers erwartet, z.B. https://seafile.example.com ", -1)])),
      _: 1,
    }, 8, ["model-value"]),
    u(t, {
      title: "Benutzername",
      subtype: "user",
      "model-value": n.backupCloud.configuration.user,
      "onUpdate:modelValue": e[1] || (e[1] = (o) => n.updateConfiguration(o, "configuration.user")),
    }, null, 8, ["model-value"]),
    u(t, {
      title: "Passwort",
      subtype: "password",
      "model-value": n.backupCloud.configuration.password,
      "onUpdate:modelValue": e[2] || (e[2] = (o) => n.updateConfiguration(o, "configuration.password")),
    }, null, 8, ["model-value"]),
    u(t, {
      title: "Bibliothek / Unterordner (optional)",
      "model-value": n.backupCloud.configuration.path,
      "onUpdate:modelValue": e[3] || (e[3] = (o) => n.updateConfiguration(o, "configuration.path")),
    }, {
      help: s(() => e[7] || (e[7] = [l(" Optionaler Pfad relativ zu /seafdav, z.B. openWB/Backup ", -1)])),
      _: 1,
    }, 8, ["model-value"]),
    u(i, {
      title: "Anzahl Backups aufbewahren",
      min: 0,
      step: 1,
      required: "",
      "model-value": n.backupCloud.configuration.max_backups ?? 0,
      "onUpdate:modelValue": e[4] || (e[4] = (o) => n.updateConfiguration(o == null || o === "" ? 0 : Number(o) || 0, "configuration.max_backups")),
    }, {
      help: s(() => e[8] || (e[8] = [l(" 0 = keine automatische Löschung; sonst werden nur die neuesten N Backups behalten. ", -1)])),
      _: 1,
    }, 8, ["model-value"]),
  ]);
}

const L = p(b, [["render", f], ["__file", "/opt/openWB-dev/openwb-ui-settings/src/components/backup_clouds/seafile/backup_cloud.vue"]]);
export { L as default };
