import { ApolloClient, ApolloProvider, InMemoryCache, split, HttpLink, from } from "@apollo/client";
import { onError, type ErrorResponse } from "@apollo/client/link/error";
import { RetryLink } from "@apollo/client/link/retry";
import { GraphQLWsLink } from "@apollo/client/link/subscriptions";
import { getMainDefinition } from "@apollo/client/utilities";
import { type GraphQLError } from "graphql";
import { createClient } from "graphql-ws";
import { v4 as uuidv4 } from "uuid";
import { errorVar } from "graphql/reactiveVars";
import { useGetToken } from "hooks/useGetToken";
import { useSignOut } from "hooks/useSignOut";
import { getEnvironmentVariable } from "utils/env";

const httpBase = getEnvironmentVariable("VITE_APOLLO_HTTP_BASE");
const wsBase = getEnvironmentVariable("VITE_APOLLO_WS_BASE");

const prepareGraphQLErrorVar = (graphQLError: GraphQLError) => {
  const { extensions: { response: { url, body: { error } = {} } = {} } = {}, message } = graphQLError;

  return {
    id: uuidv4(),
    url,
    errorCode: error?.error_code,
    errorReason: error?.reason,
    params: error?.params,
    apolloErrorMessage: message
  };
};

const ApolloClientProvider = ({ children }) => {
  const { token } = useGetToken();

  const signOut = useSignOut();

  const cache = new InMemoryCache();

  const httpLink = new HttpLink({
    uri: `${httpBase}/api`,
    headers: {
      "x-optscale-token": token
    }
  });

  const wsLink = new GraphQLWsLink(
    createClient({
      url: `${wsBase}/subscriptions`
    })
  );

  const retryLink = new RetryLink({
    attempts: { max: 3 },
    delay: { initial: 300, max: 2000, jitter: true }
  });

  const errorLink = onError(({ graphQLErrors, networkError }: ErrorResponse) => {
    if (graphQLErrors) {
      graphQLErrors.forEach((graphQLError) => {
        const { message, path, extensions } = graphQLError;

        console.log(`[GraphQL error]: Message: ${message}, Path: ${path}`);

        if (extensions?.response?.status === 401) {
          signOut();
        }
      });

      errorVar(prepareGraphQLErrorVar(graphQLErrors[0]));
    }

    /* Just log network errors for now. 
       We rely on custom error codes that are returned in graphQLErrors. 
       It might be useful to cache networkError errors to display alerts as well. 
    */
    if (networkError) {
      console.error(`[Network error]: ${networkError}`);
    }
  });

  const operationTransportLink = split(
    ({ query }) => {
      const definition = getMainDefinition(query);
      return definition.kind === "OperationDefinition" && definition.operation === "subscription";
    },
    wsLink,
    httpLink
  );

  const link = from([retryLink, errorLink, operationTransportLink]);

  const client = new ApolloClient({
    cache,
    link
  });

  return <ApolloProvider client={client}>{children}</ApolloProvider>;
};

export default ApolloClientProvider;
