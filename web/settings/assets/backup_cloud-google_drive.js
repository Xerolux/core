import { B as c } from "./DataManagement-CjZmo8Br.js";
import { _ as m, l as a, k as b, e as f, m as t, q as r, A as n, x as i } from "./vendor-JxinjXxC.js";
import "./vendor-fortawesome-DD1DIYBi.js";
import "./index-BRkE2tw3.js";
import "./vendor-bootstrap-BTTEOGLM.js";
import "./vendor-jquery-CEMonh9Y.js";
import "./vendor-axios-CL9DOa3h.js";
import "./dynamic-import-helper-BheWnx7M.js";

const g = { name: "BackupCloudGoogleDrive", mixins: [c] };
const v = { class: "backup-cloud-google-drive" };

function k(o, e, h, w, B, C) {
  const d = a("openwb-base-alert");
  const u = a("openwb-base-text-input");
  const p = a("openwb-base-heading");
  const l = a("openwb-base-button-input");
  return b(), f("div", v, [
    t(d, { subtype: "info" }, {
      default: r(() => e[4] || (e[4] = [
        n(" Zum Abruf der Zugangsberechtigung bitte die Konfiguration speichern, dann die Schritte 1-4 durchführen und danach die Konfiguration erneut speichern. ", -1),
        i("br", null, null, -1),
        n(" Auth Code und URL werden nach erfolgreicher Autorisierung wieder gelöscht. ", -1),
      ])),
      _: 1,
    }),
    t(u, {
      title: "Backupverzeichnis in Google Drive",
      subtype: "text",
      required: "",
      "model-value": o.backupCloud.configuration.backuppath,
      "onUpdate:modelValue": e[0] || (e[0] = (s) => o.updateConfiguration(s, "configuration.backuppath")),
    }, {
      help: r(() => e[5] || (e[5] = [
        n(" In diesem Verzeichnis werden die Backupdateien erstellt. Beispiel: openWB/Backup/ ", -1),
      ])),
      _: 1,
    }, 8, ["model-value"]),
    t(u, {
      title: "Client Secret",
      subtype: "password",
      "model-value": o.backupCloud.configuration.clientSecret,
      "onUpdate:modelValue": e[1] || (e[1] = (s) => o.updateConfiguration(s, "configuration.clientSecret")),
    }, {
      help: r(() => e[6] || (e[6] = [n(" Wird für den Token-Abruf genutzt (OAuth Device Flow). ", -1)])),
      _: 1,
    }, 8, ["model-value"]),
    t(u, {
      title: "Anmeldedaten auf openWB gespeichert",
      readonly: "",
      "model-value": o.backupCloud.configuration.persistent_tokencache ? "Ja" : "Nein",
    }, null, 8, ["model-value"]),
    t(p, null, {
      default: r(() => e[7] || (e[7] = [n(" Zugang zu Google Drive für diese openWB autorisieren ", -1)])),
      _: 1,
    }),
    t(l, {
      title: "1. Anmeldeanforderung erstellen",
      "button-text": "Autorisierungs-Code anfordern",
      subtype: "success",
      onButtonClicked: e[2] || (e[2] = (s) => o.sendSystemCommand("requestGoogleAuthCode", {})),
    }, {
      help: r(() => e[8] || (e[8] = [n(" Es werden Zugangstokens für Google Drive angefordert und lokal auf dieser openWB gespeichert. ", -1)])),
      _: 1,
    }),
    t(u, {
      title: "2. Diesen Code kopieren",
      subtype: "text",
      readonly: "",
      "model-value": o.backupCloud.configuration.authcode,
    }, null, 8, ["model-value"]),
    t(u, {
      title: "3. Anmelde-URL aufrufen",
      subtype: "url",
      readonly: "",
      "model-value": o.backupCloud.configuration.authurl,
    }, {
      help: r(() => e[9] || (e[9] = [n(" Diese URL im Browser öffnen und den Code eingeben. ", -1)])),
      _: 1,
    }, 8, ["model-value"]),
    t(l, {
      title: "4. Token abrufen und speichern",
      "button-text": "Autorisierungs-Token abrufen",
      subtype: "success",
      onButtonClicked: e[3] || (e[3] = (s) => o.sendSystemCommand("retrieveGoogleTokens", {})),
    }, {
      help: r(() => e[10] || (e[10] = [n(" Zugangstoken wird abgerufen und gespeichert, damit das Backup durchgeführt werden kann. ", -1)])),
      _: 1,
    }),
  ]);
}

const $ = m(g, [["render", k], ["__file", "/opt/openWB-dev/openwb-ui-settings/src/components/backup_clouds/google_drive/backup_cloud.vue"]]);
export { $ as default };
