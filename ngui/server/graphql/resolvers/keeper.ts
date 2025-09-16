import { Resolvers } from "../__generated__/types/keeper";

const resolvers: Resolvers = {
  Query: {
    events: async (_, { organizationId, requestParams }, { dataSources }) => {
      return dataSources.keeper.getEvents(organizationId, requestParams);
    },
  },
};

export default resolvers;
