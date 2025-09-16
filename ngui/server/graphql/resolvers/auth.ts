import { Resolvers } from "../__generated__/types/auth";

const resolvers: Resolvers = {
  Query: {
    organizationAllowedActions: async (
      _,
      { requestParams },
      { dataSources }
    ) => {
      return dataSources.auth.getOrganizationAllowedActions(requestParams);
    },
  },
  Mutation: {
    token: async (_, { email, password, code }, { dataSources }) => {
      return dataSources.auth.createToken({ email, password, code });
    },
    user: async (_, { email, password, name }, { dataSources }) => {
      return dataSources.auth.createUser(email, password, name);
    },
    updateUser: async (_, { id, params }, { dataSources }) => {
      return dataSources.auth.updateUser(id, params);
    },
    signIn: async (
      _,
      { provider, token, tenantId, redirectUri },
      { dataSources }
    ) => {
      return dataSources.auth.signIn(provider, token, tenantId, redirectUri);
    },
  },
};

export default resolvers;
