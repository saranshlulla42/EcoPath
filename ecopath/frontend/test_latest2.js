const { GoogleGenerativeAI } = require("@google/generative-ai");
const genAI = new GoogleGenerativeAI("AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU");

async function run() {
  try {
    const model = genAI.getGenerativeModel({ model: "gemini-flash-latest" });
    const result = await model.generateContent([
      "Identify this bird. Return its common name, scientific name, family, and key field marks. If you cannot identify it with confidence, say so. Pretend it is a blue jay.",
    ]);
    const text = result.response.text();
    console.log(text);
    const regex = /\*{0,2}(?:Scientific Name:?|Scientific name:?)\*{0,2}\s*\*{0,2}([A-Z][a-z]+\s[a-z]+)/;
    const match = text.match(regex);
    console.log("REGEX MATCH:", match ? match[1] : "FAILED");
  } catch (error) {
    console.error("ERROR in run:", error.message);
  }
}
run();
