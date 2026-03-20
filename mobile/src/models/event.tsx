export type EventPriority = 'mandatory' | 'optional';
export type EventFlexibility = 'fixed' | 'movable';
export type EventCategory = 'work' | 'study' | 'personal' | 'leisure';

export interface Event {
  id: string;
  title: string;
  startDate: string;
  endDate: string;
  duration?: number;
  location?: string;
  user_id?: number;
  priority?: EventPriority;
  flexibility?: EventFlexibility;
  category?: EventCategory;
}

export interface EventCreate {
  title: string;
  startDate: string;
  duration?: number;
  location?: string;
  priority?: EventPriority;
  flexibility?: EventFlexibility;
  category?: EventCategory;
}
