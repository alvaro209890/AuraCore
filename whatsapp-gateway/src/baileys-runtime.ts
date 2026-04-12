import { webcrypto } from "node:crypto";

if (!globalThis.crypto) {
  globalThis.crypto = webcrypto as Crypto;
}

const baileys = require("@whiskeysockets/baileys") as typeof import("@whiskeysockets/baileys");

export default baileys.default;
export const {
  Browsers,
  BufferJSON,
  DisconnectReason,
  downloadMediaMessage,
  extractMessageContent,
  fetchLatestBaileysVersion,
  initAuthCreds,
  makeCacheableSignalKeyStore,
  proto,
} = baileys;

export type {
  AuthenticationCreds,
  AuthenticationState,
  SignalDataSet,
  SignalDataTypeMap,
  SignalKeyStore,
  WASocket,
  proto as BaileysProto,
} from "@whiskeysockets/baileys";
