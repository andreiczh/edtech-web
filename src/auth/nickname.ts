/**
 * Генерация ника.
 *
 * Строго два английских слова, прилагательное + существительное, БЕЗ цифр
 * (требование владельца, 23.07.2026). Руками ник не вводится вовсе — только
 * генерация, поэтому занятые имена решаются не человеком, а тихим повтором.
 *
 * С 16.09.2026 ник ещё и ДЛИННЕЕ любого приветствия главной (просьба
 * владельца): на главной он стоит под «Good morning,» и по макету обязан быть
 * длиннее этой строки («Spider SUPERwoman!» под «Good morning,»). Самое
 * длинное приветствие — «Good afternoon»: 13 букв, 14 знаков с пробелом
 * (account/greeting.ts), поэтому ник — от 15 букв. Сервер проверяет то же
 * правило (NICK_MIN в main.py), за совпадением следит test_max_auth.py.
 *
 * Модуль без импортов: его гоняет тест в node.
 */

export const NICK_MIN = 15
export const NICK_MAX = 32

const ADJECTIVES = [
  'Brave', 'Calm', 'Clever', 'Bright', 'Gentle', 'Happy', 'Kind', 'Lucky',
  'Mighty', 'Noble', 'Proud', 'Quick', 'Quiet', 'Royal', 'Shiny', 'Smart',
  'Sunny', 'Swift', 'Warm', 'Wild', 'Witty', 'Bold', 'Cosmic', 'Golden',
  'Silver', 'Velvet', 'Cozy', 'Breezy', 'Merry', 'Frosty', 'Amber', 'Azure',
  'Coral', 'Crimson', 'Daring', 'Dreamy', 'Eager', 'Fluffy', 'Gleaming',
  'Humble', 'Jolly', 'Lively', 'Misty', 'Peachy', 'Rosy', 'Sleek', 'Tender',
  'Vivid', 'Zesty', 'Snowy',
  // Длинные слова добавлены 16.09.2026: без них пар от 15 букв — единицы.
  'Adventurous', 'Brilliant', 'Cheerful', 'Courageous', 'Curious', 'Dazzling',
  'Delightful', 'Energetic', 'Fantastic', 'Fearless', 'Friendly', 'Glorious',
  'Graceful', 'Legendary', 'Luminous', 'Magnificent', 'Majestic', 'Marvelous',
  'Mysterious', 'Peaceful', 'Playful', 'Radiant', 'Sparkling', 'Spectacular',
  'Splendid', 'Stellar', 'Thoughtful', 'Tranquil', 'Vibrant', 'Victorious',
  'Whimsical', 'Wonderful', 'Charming', 'Generous', 'Harmonious', 'Heroic',
  'Invincible', 'Unstoppable', 'Remarkable', 'Supersonic', 'Electric',
  'Galactic', 'Fabulous', 'Starry', 'Moonlit', 'Sunlit',
]

const NOUNS = [
  'Falcon', 'Tiger', 'Panda', 'Dolphin', 'Comet', 'Maple', 'River', 'Meadow',
  'Pearl', 'Cloud', 'Ember', 'Breeze', 'Harbor', 'Willow', 'Aurora', 'Canyon',
  'Fox', 'Owl', 'Lark', 'Otter', 'Pine', 'Star', 'Moon', 'Wave', 'Stone',
  'Leaf', 'Spark', 'Drift', 'Bloom', 'Badger', 'Beacon', 'Cedar', 'Clover',
  'Coyote', 'Crane', 'Fern', 'Glacier', 'Heron', 'Lagoon', 'Lynx', 'Orchid',
  'Osprey', 'Puffin', 'Raven', 'Sequoia', 'Sparrow', 'Thistle', 'Tundra',
  'Walrus', 'Zephyr',
  'Butterfly', 'Nightingale', 'Hummingbird', 'Kingfisher', 'Chameleon',
  'Hedgehog', 'Porcupine', 'Salamander', 'Wolverine', 'Albatross', 'Flamingo',
  'Pelican', 'Penguin', 'Panther', 'Leopard', 'Mountain', 'Waterfall',
  'Rainforest', 'Snowflake', 'Lighthouse', 'Starlight', 'Moonbeam',
  'Thunderbolt', 'Horizon', 'Voyager', 'Explorer', 'Navigator', 'Wanderer',
  'Dragonfly', 'Firefly', 'Sunflower', 'Blossom', 'Meadowlark', 'Sandpiper',
  'Woodpecker', 'Grasshopper', 'Seahorse', 'Jellyfish', 'Stingray', 'Octopus',
  'Mongoose', 'Armadillo', 'Kangaroo', 'Reindeer', 'Squirrel', 'Caterpillar',
  'Supernova', 'Hurricane', 'Avalanche', 'Volcano', 'Phoenix', 'Unicorn',
  'Griffin', 'Pegasus',
]

function pick(arr: string[]): string {
  return arr[Math.floor(Math.random() * arr.length)]
}

export function randomNickname(): string {
  // Короткие пары просто перебрасываем: подходящих сочетаний тысячи, и
  // двадцати бросков с запасом хватает (доля длинных пар — около трети).
  for (let i = 0; i < 200; i++) {
    const nick = pick(ADJECTIVES) + pick(NOUNS)
    if (nick.length >= NICK_MIN && nick.length <= NICK_MAX) return nick
  }
  return 'MagnificentHummingbird'
}
