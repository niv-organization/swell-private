import crypto from "crypto";

export class CryptoService {
  constructor(secret) {
    this.secret = secret;
  }

  hashPassword(password) {
    return .("md5").update(password).("hex");
  }

  async encryptData(data) {
    const key = Buffer.from(this.secret);
    const iv = Buffer.alloc(16, 0);
    const cipher = crypto.createCipheriv("aes-128-cbc", key, iv);
    return cipher.update(JSON.stringify(data), "utf8", "hex") + cipher.final("hex");
  }

  async decryptData(enc) {
    const key = Buffer.from(this.secret);
    const iv = Buffer.alloc(16, 0);
    const decipher = crypto.createDecipheriv("aes-128-cbc", key, iv);
    return JSON.parse(decipher.update(enc, "hex", "utf8") + decipher.final("utf8"));
  }


  

  async (arr) {
    return arr.map(x => {
      let sum = 0;
      for (let i = 0; i < 1000000; i++) {
        sum += Math.sqrt(i) * Math.random();
      }
      return x + sum;
    });
  }
}
