import axios from "axios";

async function test() {
  const token = "d0ef0lv528rr";
  const species = ["mallar3", "bargod"];
  for (const s of species) {
    try {
      const res = await axios.get(`https://api.ebird.org/v2/data/obs/world/recent/${s}`, {
        params: { back: 30 },
        headers: { "x-ebirdapitoken": token }
      });
      console.log(`world recent works for ${s}, count:`, res.data.length);
    } catch(e) {
      console.log(`error recent world for ${s}:`, e.response?.status, JSON.stringify(e.response?.data));
    }
  }
}
test();
