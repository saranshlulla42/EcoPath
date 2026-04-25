const { GoogleGenerativeAI } = require("@google/generative-ai");
const genAI = new GoogleGenerativeAI("AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU");

async function run() {
  const result = await fetch(`https://generativelanguage.googleapis.com/v1beta/models?key=AIzaSyBxtM3vFlQwtAKQy2qx9JHEjbx3OJY9tRU`);
  const data = await result.json();
  console.log(data);
}
run();
