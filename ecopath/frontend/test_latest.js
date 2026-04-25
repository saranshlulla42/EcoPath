const { GoogleGenerativeAI } = require("@google/generative-ai");
const genAI = new GoogleGenerativeAI("AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU");

async function run() {
  try {
    const model = genAI.getGenerativeModel({ model: "gemini-flash-latest" });
    const result = await model.generateContent(["Identify this bird"]);
    console.log(result.response.text());
  } catch (error) {
    console.error("ERROR in run:", error.message);
  }
}
run();
