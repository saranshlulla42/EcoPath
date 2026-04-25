import axios from "axios";
import fs from "fs";

async function test() {
  const token = "d0ef0lv528rr";
  try {
    const res2 = await axios.get(`https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json`, {
      headers: { "x-ebirdapitoken": token }
    });
    fs.writeFileSync("taxonomy_sample.json", JSON.stringify(res2.data.slice(0, 5), null, 2));
    console.log("taxonomy written");
  } catch(e) {
    console.log("error taxonomy:", e.response?.status, e.response?.data);
  }
}
test();
