type Entity = {
  id: string;
  slug: string;
  name: string;
};

type UserData = {
  sourceId: string;
  firmSlug?: string;
  displayName?: string;
};

export class EntityService {
  createEntity(userData: UserData): Entity {
    const entity: Entity = {
      id: userData.sourceId,
      slug: userData.firmSlug ?? '',
      name: userData.displayName ?? '',
    };
    return entity;
  }
}
