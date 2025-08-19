import { makeExecutableSchema } from "@graphql-tools/schema";
import { mergeTypeDefs, mergeResolvers } from "@graphql-tools/merge";
import { loadFilesSync } from "@graphql-tools/load-files";
import path from "path";

const __dirname = import.meta.dirname;

const typeDefs = loadFilesSync(path.join(__dirname, "typeDefs", "**", "*.{js,ts,graphql}"));
const resolvers = loadFilesSync(path.join(__dirname, "resolvers", "**", "*.{js,ts,graphql}"));

export const schema = makeExecutableSchema({
  typeDefs: mergeTypeDefs(typeDefs),
  resolvers: mergeResolvers(resolvers)
});
