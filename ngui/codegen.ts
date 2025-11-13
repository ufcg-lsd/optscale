import type { CodegenConfig } from "@graphql-codegen/cli";

const auth = {
  "./server/graphql/__generated__/types/auth.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/auth/*.ts"],
    plugins: ["typescript", "typescript-resolvers"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      contextType: "../../../server#ContextValue"
    }
  },
  "./ui/src/graphql/__generated__/hooks/auth.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/auth/*.ts"],
    documents: "./ui/src/graphql/queries/auth/*.graphql",
    plugins: ["typescript", "typescript-operations", "typescript-react-apollo"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      withHooks: true,
      withMutationFn: true,
      withRefetchFn: true,
      reactApolloVersion: 3
    }
  }
};

const restapi = {
  "./server/graphql/__generated__/types/restapi.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/restapi/*.ts"],
    plugins: ["typescript", "typescript-resolvers"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      contextType: "../../../server#ContextValue",
      scalars: {
        JSONObject: "Record<string, unknown>"
      }
    }
  },
  "./ui/src/graphql/__generated__/hooks/restapi.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/restapi/*.ts"],
    documents: "./ui/src/graphql/queries/restapi/*.graphql",
    plugins: ["typescript", "typescript-operations", "typescript-react-apollo"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      withHooks: true,
      withMutationFn: true,
      withRefetchFn: true,
      reactApolloVersion: 3,
      scalars: {
        JSONObject: "Record<string, unknown>"
      }
    }
  }
};

const keeper = {
  "./server/graphql/__generated__/types/keeper.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/keeper/*.ts"],
    plugins: ["typescript", "typescript-resolvers"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      contextType: "../../../server#ContextValue"
    }
  },
  "./ui/src/graphql/__generated__/hooks/keeper.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/keeper/*.ts"],
    documents: "./ui/src/graphql/queries/keeper/*.graphql",
    plugins: ["typescript", "typescript-operations", "typescript-react-apollo"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      withHooks: true,
      withMutationFn: true,
      withRefetchFn: true,
      reactApolloVersion: 3
    }
  }
};

const slacker = {
  "./server/graphql/__generated__/types/slacker.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/slacker/*.ts"],
    plugins: ["typescript", "typescript-resolvers"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      contextType: "../../../server#ContextValue"
    }
  },
  "./ui/src/graphql/__generated__/hooks/slacker.ts": {
    schema: ["./server/graphql/typeDefs/root.ts", "./server/graphql/typeDefs/slacker/*.ts"],
    documents: "./ui/src/graphql/queries/slacker/*.graphql",
    plugins: ["typescript", "typescript-operations", "typescript-react-apollo"],
    config: {
      skipTypename: false,
      enumsAsTypes: true,
      defaultScalarType: "unknown",
      withHooks: true,
      withMutationFn: true,
      withRefetchFn: true,
      reactApolloVersion: 3
    }
  }
};

const config: CodegenConfig = {
  overwrite: true,
  verbose: true,
  debug: true,
  hooks: {
    afterAllFileWrite: ["prettier --write"]
  },
  generates: {
    ...auth,
    ...restapi,
    ...keeper,
    ...slacker
  }
};

export default config;
