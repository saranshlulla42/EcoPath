const { GoogleGenerativeAI } = require("@google/generative-ai");
const genAI = new GoogleGenerativeAI("AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU");
const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });

async function run() {
  try {
    const result = await model.generateContent(["test"]);
    console.log(result.response.text());
  } catch (error) {
    console.error("ERROR:", error);
  }
}
run();
