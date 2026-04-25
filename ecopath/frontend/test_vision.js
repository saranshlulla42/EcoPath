const { GoogleGenerativeAI } = require("@google/generative-ai");
const genAI = new GoogleGenerativeAI("AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU");

async function run() {
  try {
    const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash" });
    const result = await model.generateContent([
      "Identify this bird. Return its common name, scientific name, family, and key field marks. If you cannot identify it with confidence, say so.",
    ]);
    const text = result.response.text();
    console.log("Response:", text);
    const match = text.match(/\*{0,2}(?:Scientific Name:?|Scientific name:?)\*{0,2}\s*\*{0,2}([A-Z][a-z]+\s[a-z]+)/);
    console.log("Regex match:", match ? match[1] : "MATCH_FAILED");
  } catch (error) {
    console.error("ERROR:", error.message || error);
  }
}
run();
