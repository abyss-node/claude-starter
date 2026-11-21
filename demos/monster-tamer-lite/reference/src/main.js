// The page. Rules live in the other modules; this file only wires them to the DOM.
import { SPECIES } from './data.js';
import { createRng, nextFloat } from './rng.js';
import { makeCreature } from './rules.js';
import { createBattle, legalActions, resolveTurn, activeOf } from './battle.js';
import { chooseAction } from './ai.js';
import { createDuel, duelContinue, duelPick, duelView } from './duel.js';
import { createGame, walk, endBattle, saveGame, loadGame } from './game.js';
import { createAudio } from './audio.js';
import { drawMap, drawBattle, drawBlank } from './draw.js';

const $ = (id) => document.getElementById(id);
const ctx = $('screen').getContext('2d');
const audio = createAudio();
const SAVE_KEY = 'monster-tamer-lite-save';
let mode = null;
let game = null;
let solo = null;
let duel = null;

const say = (text) => { $('message').textContent = text; };
const seedValue = () => {
  const n = Number($('seed').value.trim());
  return Number.isInteger(n) && n >= 0 && n <= 4294967295 ? n : 1;
};

function teamFor(seed, offset) {
  const rng = createRng(seed + offset);
  const pool = SPECIES.slice();
  const team = [];
  while (team.length < 3 && pool.length) team.push(makeCreature(pool.splice(Math.floor(nextFloat(rng) * pool.length), 1)[0], 10));
  return team;
}

function describe(action, battle, side) {
  const me = activeOf(battle, side);
  if (action.kind === 'move') return `${me.moves[action.slot].name} (${me.moves[action.slot].type}, ${me.moves[action.slot].power})`;
  if (action.kind === 'switch') return `Switch to ${battle.sides[side].team[action.to].name}`;
  return `Snare (${battle.snares} left)`;
}

function showMenu(battle, side, onPick) {
  const menu = $('menu');
  menu.replaceChildren();
  for (const action of legalActions(battle, side)) {
    const b = document.createElement('button');
    b.textContent = describe(action, battle, side);
    b.addEventListener('click', () => onPick(action));
    menu.append(b);
  }
}
const clearMenu = () => $('menu').replaceChildren();

function logText(entries, battle) {
  const name = (side) => activeOf(battle, side).name;
  return entries.map((e) => {
    if (e.type === 'move') return `${name(e.side)} used ${e.move}.`;
    if (e.type === 'miss') return 'It missed.';
    if (e.type === 'damage') return `${e.amount} damage to ${battle.sides[e.side].name} (${e.cause}).`;
    if (e.type === 'status') return `${e.kind} takes hold.`;
    if (e.type === 'cured') return `${e.kind} wears off.`;
    if (e.type === 'skip') return 'Too dazed to act.';
    if (e.type === 'faint') return `${battle.sides[e.side].name}'s creature fainted.`;
    if (e.type === 'switch') return `${battle.sides[e.side].name} switched creatures.`;
    if (e.type === 'snare') return e.success ? 'The snare held!' : 'The snare snapped.';
    if (e.type === 'end') return e.winner === -1 ? 'A draw.' : `${battle.sides[e.winner].name} wins.`;
    return '';
  }).filter(Boolean).join(' ');
}

// One human on side 0 against the computer on side 1 (adventure and solo mode).
function humanTurn(battle, action, afterOver) {
  const before = battle.log.length;
  resolveTurn(battle, [action, chooseAction(battle, 1)]);
  while (battle.phase === 'replace' && !battle.pending[0]) resolveTurn(battle, [null, chooseAction(battle, 1)]);
  audio.hit();
  say(logText(battle.log.slice(before), battle));
  drawBattle(ctx, battle);
  if (battle.phase === 'over') { clearMenu(); afterOver(); return; }
  showMenu(battle, 0, (a) => humanTurn(battle, a, afterOver));
}

function afterAdventureBattle() {
  const res = endBattle(game);
  if (res.result === 'caught') { audio.catchOk(); say(`Caught! It joins your party. (${game.party.length} in party)`); }
  else if (res.result === 'won') say(`You won. Each standing creature gained ${res.xp} XP.`);
  else say('You blacked out and woke at the start, healed.');
  try { localStorage.setItem(SAVE_KEY, saveGame(game)); } catch { /* storage may be blocked */ }
  setTimeout(() => drawMap(ctx, game), 600);
}

function startAdventure() {
  mode = 'adventure';
  let loaded = null;
  try { const t = localStorage.getItem(SAVE_KEY); if (t) loaded = loadGame(t); } catch { loaded = null; }
  game = loaded || createGame(seedValue());
  clearMenu();
  say(loaded ? 'Save loaded. Arrow keys or WASD to walk.' : 'A new adventure. Arrow keys or WASD to walk; tall grass hides creatures; + heals.');
  if (game.battle) { drawBattle(ctx, game.battle); showMenu(game.battle, 0, (a) => humanTurn(game.battle, a, afterAdventureBattle)); } else drawMap(ctx, game);
}

function startSolo() {
  mode = 'solo';
  const seed = seedValue();
  solo = createBattle({ seed, sides: [{ name: 'You', team: teamFor(seed, 1) }, { name: 'Computer', team: teamFor(seed, 2) }] });
  say('Solo battle. Defeat all three of the computer\'s creatures.');
  drawBattle(ctx, solo);
  showMenu(solo, 0, (a) => humanTurn(solo, a, () => say(`${solo.winner === 0 ? 'You win!' : 'The computer wins.'} Pick a mode to play again.`)));
}

function renderDuel() {
  const v = duelView(duel);
  clearMenu();
  const cover = $('cover');
  if (v.stage === 'handoff') {
    $('cover-text').textContent = `Pass the device to ${v.names[v.who]}. Nobody else looks.`;
    cover.classList.add('on');
    drawBlank(ctx, 'Hidden');
  } else {
    cover.classList.remove('on');
    drawBattle(ctx, duel.battle);
  }
  if (v.stage === 'pick') {
    say(`${v.names[v.who]}: choose in secret.`);
    showMenu(duel.battle, v.who, (a) => { duelPick(duel, v.who, a); renderDuel(); });
  } else if (v.stage === 'result') {
    say(logText(v.log, duel.battle));
    const b = document.createElement('button');
    b.textContent = 'Next';
    b.addEventListener('click', () => { duelContinue(duel); renderDuel(); });
    $('menu').append(b);
  } else if (v.stage === 'over') say(v.winner === -1 ? 'A draw.' : `${v.names[v.winner]} wins! Pick a mode to play again.`);
}

function startDuel() {
  mode = 'duel';
  const seed = seedValue();
  duel = createDuel({ seed, sides: [{ name: 'Player 1', team: teamFor(seed, 1) }, { name: 'Player 2', team: teamFor(seed, 2) }] });
  renderDuel();
}

$('cover-ready').addEventListener('click', () => { duelContinue(duel); renderDuel(); });
$('mode-adventure').addEventListener('click', startAdventure);
$('mode-solo').addEventListener('click', startSolo);
$('mode-duel').addEventListener('click', startDuel);
$('sound').addEventListener('click', () => { $('sound').textContent = `Sound: ${audio.toggle() ? 'on' : 'off'}`; });

const KEYS = { ArrowUp: 'n', w: 'n', ArrowRight: 'e', d: 'e', ArrowDown: 's', s: 's', ArrowLeft: 'w', a: 'w' };
window.addEventListener('keydown', (e) => {
  if (mode !== 'adventure' || !game || game.battle || !KEYS[e.key]) return;
  e.preventDefault();
  const before = game.party.map((c) => c.hp).join();
  const r = walk(game, KEYS[e.key]);
  if (game.party.map((c) => c.hp).join() !== before) audio.heal();
  if (r.encounter) {
    say(`A ${game.battle.sides[1].team[0].name} appears!`);
    drawBattle(ctx, game.battle);
    showMenu(game.battle, 0, (a) => humanTurn(game.battle, a, afterAdventureBattle));
  } else drawMap(ctx, game);
});

drawBlank(ctx, 'Monster Tamer Lite');
