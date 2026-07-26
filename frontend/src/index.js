
function isApiRequest(pathname) {
  return pathname === "/api" || pathname.startsWith("/api/");
}

function buildBackendRequest(request, backendOrigin) {
  const incomingUrl = new URL(request.url);
  const backendUrl = new URL(backendOrigin);
  backendUrl.pathname = incomingUrl.pathname.replace(/^\/api\/?/, "/");
  backendUrl.search = incomingUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.set("x-forwarded-host", incomingUrl.host);
  headers.set("x-forwarded-proto", incomingUrl.protocol.replace(":", ""));

  const init = {
    method: request.method,
    headers,
    redirect: "manual",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  return new Request(backendUrl, init);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (isApiRequest(url.pathname)) {
      try {
        return fetch(buildBackendRequest(request, env.BACKEND_ORIGIN));
      } catch (error) {
        return new Response(error.message, { status: 500 });
      }
    }

    return env.ASSETS.fetch(request);
  },
};
