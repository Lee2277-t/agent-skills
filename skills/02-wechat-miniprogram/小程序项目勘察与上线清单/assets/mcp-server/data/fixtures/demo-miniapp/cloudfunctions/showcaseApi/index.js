const routes = require("./route");

function resolveHandler(target) {
  const [controllerName, methodName] = String(target || "").split("@");
  if (!controllerName || !methodName) return null;
  const controller = require(`./controller/${controllerName}`);
  return typeof controller[methodName] === "function" ? controller[methodName] : null;
}

exports.main = async function main(event, context) {
  const route = event.route || "";
  const handler = resolveHandler(routes[route]);
  if (!handler) return { ok: false, code: "ROUTE_NOT_FOUND" };
  return handler(event, context);
};
