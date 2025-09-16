import { gql } from "graphql-tag";

export default gql`
  type Event {
    time: Int
    level: String
    evt_class: String
    object_id: String
    object_type: String
    object_name: String
    organization_id: String
    description: String
    ack: Boolean
    localized: String
    id: String
    read: Boolean
    acknowledged_user: String
  }

  enum EventLevel {
    INFO
    WARNING
    ERROR
    DEBUG
  }

  # TODO: circle back on types - required types must be exclamated (see organizationId below and generated resolversTypes)
  input EventsRequestParams {
    limit: Int = 80
    level: [EventLevel!]
    time_start: Int
    time_end: Int
    last_id: String
    include_read: Boolean = true
    read_on_get: Boolean = true
    description_like: String
  }

  type Query {
    events(organizationId: ID!, requestParams: EventsRequestParams): [Event]
  }
`;
