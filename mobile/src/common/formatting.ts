export const formatDuration = (duration?: number) => {
  if (!duration || duration === 0) return "Not specified";
  const hours = Math.floor(duration / 60);
  const minutes = duration % 60;

  if (hours > 0 && minutes > 0) {
    return `${hours} hours ${minutes} minutes`;
  } else if (hours > 0) {
    if (hours === 1) return "1 hour";
    else return `${hours} hours`;
  } else {
    return `${minutes} minutes`;
  }
};

export const formatLocation = (location?: string) => {
  if (!location) return "Not specified";
  return location;
};
