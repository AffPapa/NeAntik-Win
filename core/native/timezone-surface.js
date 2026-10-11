function timezoneSurface() {
  return {
    zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    winter: new Date('2026-01-15T12:00:00Z').getTimezoneOffset(),
    summer: new Date('2026-07-15T12:00:00Z').getTimezoneOffset(),
    beforeDST: new Date('2026-03-29T00:30:00Z').getTimezoneOffset(),
    afterDST: new Date('2026-03-29T01:30:00Z').getTimezoneOffset(),
    formatted: new Intl.DateTimeFormat('en-US', {
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
    }).format(new Date('2026-01-15T12:00:00Z'))
  };
}
