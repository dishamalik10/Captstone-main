/**
 * AURA's privacy policy, shown in the app (Profile → Privacy and data) and before sign-up.
 *
 * DRAFT written from what the code actually does (ENGINEERING_PLAN 4.3). The owner must
 * review it, fill in the contact address and effective date, and keep it in step with
 * the code before the public release.
 */
export const PRIVACY_POLICY_UPDATED = '2026-11-27';

export const PRIVACY_POLICY: { heading: string; body: string[] }[] = [
  {
    heading: 'Who runs AURA',
    body: [
      'AURA is a free, non-commercial student project. It runs on a single computer operated by its developer, reached over the internet through Cloudflare. There are no ads and nothing is sold.',
    ],
  },
  {
    heading: 'What AURA stores',
    body: [
      'Your account: name, email address and a salted hash of your password (never the password itself).',
      'Your wardrobe: the clothing photos you upload or import from a shop link, and the details AURA detects or you correct.',
      'Your profile and preferences: style preferences, sizes, height, body shape and skin tone, if you enter them.',
      'Your body photos, only if you choose to use My Virtual Look and confirm the consent statement: the avatar made from your photo, its body analysis, and the try-on looks you render.',
      'Your body measurements (chest, waist, hip and similar, in cm), if you type them or ask AURA to estimate them. For an estimate you add a side photo: it is measured and then discarded straight away; only the numbers are kept.',
      'Your activity: chats with the AI stylist, outfit reactions (likes, saves, wears), and the outfits shown to you, used to personalise your recommendations.',
      'Marketplace and social: your listings and their photos, orders including the shipping name, phone and address you enter, messages with other users, and your posts, likes and follows.',
      'Technical records: server logs of which page was requested, when, and the result (kept in rotating files of limited size), and short-lived rate-limit records that include your network address (deleted within a day).',
    ],
  },
  {
    heading: 'How it is used',
    body: [
      'Only to run AURA for you: to organise your wardrobe, recommend and explain outfits, render try-on previews, and run the marketplace and social features.',
      'All AI models (garment recognition, outfit ranking, the stylist chat and virtual try-on) run on AURA\'s own computer. Your photos and messages are not sent to any outside AI service.',
    ],
  },
  {
    heading: 'Who else sees your data',
    body: [
      'Other AURA users see what you choose to share: listings and their photos, your public profile and posts, and your messages to them. A seller sees the shipping details you enter for their order.',
      'Your body photos, avatar, measurements, try-on looks and wardrobe photos are private to you; photos are shown only through links that expire. Size advice on a listing is worked out for you alone and never shown to the seller.',
      'Outside services: Cloudflare carries the traffic between your device and AURA. When you ask for weather, the city name is sent to OpenWeatherMap. When you import from a shop link, AURA\'s server downloads that page and its photo.',
    ],
  },
  {
    heading: 'How long it is kept',
    body: [
      'Until you delete it. Unsaved try-on looks are deleted automatically after 7 days. A sign-in lasts 30 days in the app and 7 days on the web.',
    ],
  },
  {
    heading: 'Your choices',
    body: [
      'Delete my body data (in My Virtual Look or Privacy and data) permanently removes your body photos, avatar, body analysis, body measurements, height and every try-on look, and withdraws your consent.',
      'Delete my account (in Privacy and data) permanently removes your account and everything it owns. Orders you took part in stay in the other person\'s history, shown as "Deleted user" and without your address.',
      'Log out of all devices ends every sign-in at once.',
      'You can correct your details at any time in Edit profile.',
    ],
  },
  {
    heading: 'Age',
    body: ['You must be 18 or over to add a body photo.'],
  },
  {
    heading: 'Contact',
    body: ['Questions or requests: use the address on the Help and support screen.'],
  },
];
