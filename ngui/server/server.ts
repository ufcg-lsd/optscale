import { ApolloServer } from "@apollo/server";
import { expressMiddleware } from "@apollo/server/express4";
import { ApolloServerPluginDrainHttpServer } from "@apollo/server/plugin/drainHttpServer";
import express from "express";
import http from "http";
import cors from "cors";
import path from "path";
import bodyParser from "body-parser";
import { createProxyMiddleware } from "http-proxy-middleware";
import checkEnvironment from "./checkEnvironment.js";
import KeeperClient from "./api/keeper/client.js";
import SlackerClient from "./api/slacker/client.js";
import RestApiClient from "./api/restapi/client.js";
import AuthClient from "./api/auth/client.js";
import { schema } from "./graphql/schema.js";

if (process.env.NODE_ENV === "development") {
  const dotenv = await import("dotenv");
  const dotenvExpand = await import("dotenv-expand");
  const myEnv = dotenv.config();
  dotenvExpand.expand(myEnv);
}

checkEnvironment(["UI_BUILD_PATH", "PROXY_URL"]);

const app = express();

const httpServer = http.createServer(app);

export interface ContextValue {
  dataSources: {
    keeper: KeeperClient;
    slacker: SlackerClient;
    restapi: RestApiClient;
    auth: AuthClient;
  };
}

const server = new ApolloServer<ContextValue>({
  schema,
  plugins: [ApolloServerPluginDrainHttpServer({ httpServer })]
});

// Ensure we wait for our server to start
await server.start();

// Set up our Express middleware to handle CORS, body parsing,
// and our expressMiddleware function.
app.use(
  "/api",
  cors<cors.CorsRequest>(),
  bodyParser.json(),
  // expressMiddleware accepts the same arguments:
  // an Apollo Server instance and optional configuration options
  expressMiddleware(server, {
    context: async ({ req }) => {
      const { cache } = server;

      const token = req.headers["x-optscale-token"] as string;

      return {
        // We create new instances of our data sources with each request,
        // passing in our server's cache.
        dataSources: {
          keeper: new KeeperClient({ cache }, token, "http://keeper"),
          slacker: new SlackerClient({ cache }, token, "http://slacker"),
          restapi: new RestApiClient({ cache }, token, "http://restapi"),
          auth: new AuthClient({ cache }, token, "http://auth")
        }
      };
    }
  })
);

// Temporary proxy until we migrate the APIs.
const proxyMiddleware = createProxyMiddleware({
  target: process.env.PROXY_URL,
  changeOrigin: true,
  secure: false
});

app.use("/auth", proxyMiddleware);
app.use("/jira_bus", proxyMiddleware);
app.use("/restapi", proxyMiddleware);

const UI_BUILD_PATH = process.env.UI_BUILD_PATH;

// Serve static build
app.use(express.static(path.join(UI_BUILD_PATH, "build")));

app.get("/*", function (req, res) {
  res.sendFile(path.join(UI_BUILD_PATH, "build", "index.html"));
});

// Modified server startup
await new Promise<void>((resolve) => httpServer.listen({ port: 4000 }, resolve));
console.log(`🚀 Server ready at http://localhost:4000/`);
