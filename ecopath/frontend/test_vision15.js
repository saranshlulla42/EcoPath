const { GoogleGenerativeAI } = require("@google/generative-ai");
const genAI = new GoogleGenerativeAI(process.env.NEXT_PUBLIC_GEMINI_API_KEY || "AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU");

async function run() {
  try {
    const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });
    const result = await model.generateContent([
      "Identify this bird. Return its common name, scientific name, family, and key field marks. If you cannot identify it with confidence, say so.",
    ]);
    const text = result.response.text();
    console.log("Raw output:\n", text);
    const regex = /\*{0,2}(?:Scientific Name:?|Scientific name:?)\*{0,2}\s*\*{0,2}([A-Z][a-z]+\s[a-z]+)/;
    const match = text.match(regex);
    console.log("Regex match:", match ? match[1] : "MATCH_FAILED");
  } catch (error) {
    console.error("ERROR in run:", error);
  }
}
run();
