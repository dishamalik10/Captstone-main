/**
 * Landing page copy and sample data. Every garment and outfit here is demo
 * content for illustration; none of it comes from a user's account.
 */
const img = (id: string, w = 600, h = 750) =>
  `https://images.unsplash.com/${id}?w=${w}&h=${h}&fit=crop`;

export interface SampleGarment {
  id: string;
  name: string;
  category: string;
  colour: string;
  pattern: string;
  image: string;
}

export const GARMENTS: Record<string, SampleGarment> = {
  shirt: { id: 'shirt', name: 'Linen shirt', category: 'Top', colour: 'White', pattern: 'Solid', image: img('photo-1596755094514-f87e34085b2c') },
  chinos: { id: 'chinos', name: 'Slim chinos', category: 'Bottom', colour: 'Khaki', pattern: 'Solid', image: img('photo-1473966968600-fa801b869a1a') },
  sneakers: { id: 'sneakers', name: 'White sneakers', category: 'Shoes', colour: 'White', pattern: 'Solid', image: img('photo-1549298916-b41d501d3772') },
  watch: { id: 'watch', name: 'Gold watch', category: 'Accessory', colour: 'Gold', pattern: 'Solid', image: img('photo-1523275335684-37898b6baf30') },
  blazer: { id: 'blazer', name: 'Navy blazer', category: 'Top', colour: 'Navy', pattern: 'Solid', image: img('photo-1594938298603-c8148c4dae35') },
  tee: { id: 'tee', name: 'Black tee', category: 'Top', colour: 'Black', pattern: 'Solid', image: img('photo-1521572163474-6864f9cf17ab') },
  denim: { id: 'denim', name: 'Dark denim', category: 'Bottom', colour: 'Indigo', pattern: 'Solid', image: img('photo-1542272604-787c3835535d') },
  sweater: { id: 'sweater', name: 'Cashmere sweater', category: 'Top', colour: 'Camel', pattern: 'Solid', image: img('photo-1576566588028-4147f3842f27') },
  cargo: { id: 'cargo', name: 'Cargo pants', category: 'Bottom', colour: 'Olive', pattern: 'Solid', image: img('photo-1591195853828-11db59a44f6b') },
  runners: { id: 'runners', name: 'Running shoes', category: 'Shoes', colour: 'Grey', pattern: 'Solid', image: img('photo-1606107557195-0e29a4b5b4aa') },
  scarf: { id: 'scarf', name: 'Silk scarf', category: 'Accessory', colour: 'Red', pattern: 'Printed', image: img('photo-1601924994987-69e26d50dc26') },
  blouse: { id: 'blouse', name: 'Silk blouse', category: 'Top', colour: 'Beige', pattern: 'Solid', image: img('photo-1564257631407-4deb1f99d992') },
  polo: { id: 'polo', name: 'Striped polo', category: 'Top', colour: 'Blue', pattern: 'Striped', image: img('photo-1586363104862-3a5e2ab60d99') },
  dress: { id: 'dress', name: 'Midi dress', category: 'Dress', colour: 'Emerald', pattern: 'Solid', image: img('photo-1595777457583-95e059d581b8') },
};

export interface SampleOutfit {
  occasion: string;
  name: string;
  weather: string;
  image: string;
  pieces: string[];
  why: string;
}

export const DEMO_OUTFITS: SampleOutfit[] = [
  {
    occasion: 'Casual',
    name: 'Summer brunch',
    weather: '31°C and sunny',
    image: img('photo-1496747611176-843222e1e57c', 900, 1150),
    pieces: ['shirt', 'chinos', 'sneakers', 'watch'],
    why: 'Linen and neutral tones stay light in the heat, and white sneakers keep it relaxed.',
  },
  {
    occasion: 'Meeting',
    name: 'Boardroom ready',
    weather: '22°C and clear',
    image: img('photo-1507679799987-c73779587ccf', 900, 1150),
    pieces: ['blazer', 'shirt', 'chinos', 'watch'],
    why: 'A navy blazer over a crisp shirt reads polished; khaki chinos stop it feeling stiff.',
  },
  {
    occasion: 'Date',
    name: 'Date night',
    weather: '18°C, light breeze',
    image: img('photo-1515372039744-b8f02a3ae446', 900, 1150),
    pieces: ['tee', 'denim', 'sneakers', 'watch'],
    why: 'Dark denim and a fitted black tee: simple, sharp and easy to move in.',
  },
  {
    occasion: 'Travel',
    name: 'Long day in transit',
    weather: '9°C and overcast',
    image: img('photo-1434389677669-e08b4cac3105', 900, 1150),
    pieces: ['sweater', 'cargo', 'runners', 'scarf'],
    why: 'Soft cashmere and roomy cargos for hours of sitting; running shoes for the walking.',
  },
];

export const DEMO_WARDROBE = [
  'shirt', 'chinos', 'sneakers', 'watch', 'blazer', 'tee',
  'denim', 'sweater', 'cargo', 'runners', 'scarf', 'blouse',
];

export const PROBLEM_RAIL = [
  'blazer', 'tee', 'denim', 'blouse', 'polo', 'sweater', 'cargo', 'dress', 'chinos', 'scarf',
];

export const PAINS = [
  'The same few pieces, on repeat.',
  'Dressing for weather you didn’t check.',
  'An invitation, and no idea what works.',
];

export const STEPS = [
  {
    n: '01',
    title: 'Upload your wardrobe',
    body: 'Photograph each piece. AURA tags its category, colour and pattern, and you can correct it.',
  },
  {
    n: '02',
    title: 'AURA learns what works',
    body: 'A compatibility model judges which pieces belong together. Your likes and skips count too.',
  },
  {
    n: '03',
    title: 'Discover your next outfit',
    body: 'Choose an occasion and get a complete look from your own clothes, with the reasons why.',
  },
];

export const FACTORS = [
  { icon: 'calendar-outline', name: 'Occasion', line: 'Seven to choose from, from interviews to weddings.' },
  { icon: 'partly-sunny-outline', name: 'Weather', line: 'Add your city and today’s conditions shape the look.' },
  { icon: 'heart-outline', name: 'Preferences', line: 'Minimalist, streetwear, vintage, or all three.' },
  { icon: 'body-outline', name: 'Body type', line: 'Guides proportions only. Every shape is a good shape.' },
  { icon: 'color-palette-outline', name: 'Skin tone', line: 'Suggests colours you may enjoy. Your taste wins.' },
] as const;

export const PIPELINE = [
  {
    stage: 'See',
    model: 'EfficientNetV2B0 encoder',
    line: 'A custom CNN turns each garment photo into an embedding.',
  },
  {
    stage: 'Match',
    model: 'Compatibility transformer',
    line: 'Trained on the Polyvore outfit dataset to judge which pieces work together.',
  },
  {
    stage: 'Explain',
    model: 'Stylist LLM',
    line: 'Qwen2.5-1.5B, fine-tuned with LoRA, picks from candidate outfits and says why.',
  },
  {
    stage: 'Wear',
    model: 'Your recommendation',
    line: 'A complete look built only from what you own.',
  },
];

export const FAQ = [
  {
    q: 'What do I need to get started?',
    a: 'An account and photos of clothes you already own. Start with a few pieces and add more over time.',
  },
  {
    q: 'How does AURA decide what goes together?',
    a: 'An image model describes each garment, a compatibility model scores combinations, and a stylist language model chooses an outfit and explains its reasoning.',
  },
  {
    q: 'Does it take the weather into account?',
    a: 'Yes. Add your city to your profile and recommendations consider the current conditions there.',
  },
  {
    q: 'Do I have to share my body type or skin tone?',
    a: 'They help tailor proportions and colour suggestions, and you can update them at any time from your profile. Suggestions are a starting point, never a rule.',
  },
  {
    q: 'What if AURA labels a garment wrongly?',
    a: 'You can review every upload and correct its details, including its category. Your corrections are saved to your wardrobe.',
  },
  {
    q: 'Can I ask the stylist questions?',
    a: 'Yes. In chat you can ask for an occasion, a colour or a weather-ready look, and answers draw on your own wardrobe.',
  },
];
