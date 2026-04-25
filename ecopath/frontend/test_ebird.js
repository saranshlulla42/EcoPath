import axios from "axios";

async function test() {
  const token = "d0ef0lv528rr";
  const species = "bartgo";
  try {
    const res = await axios.get(`https://api.ebird.org/v2/data/obs/world/recent/${species}`, {
      params: { back: 30 },
      headers: { "x-ebirdapitoken": token }
    });
    console.log("world recent works, count:", res.data.length);
  } catch(e) {
    console.log("error recent world:", e.response?.status, e.response?.data);
  }

  try {
    const res2 = await axios.get(`https://api.ebird.org/v2/ref/taxonomy/ebird?fmt=json`, {
      headers: { "x-ebirdapitoken": token }
    });
    console.log("taxonomy works, count:", res2.data.length);
  } catch(e) {
    console.log("error taxonomy:", e.response?.status, e.response?.data);
  }
}
test();
