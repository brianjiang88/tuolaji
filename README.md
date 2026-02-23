# tuolaji

For rules, refer to this link:
https://static1.squarespace.com/static/5942f94fb8a79b3aa562e99d/t/62c340d68ede295f34d37bb4/1656963287304/An_Introduction_To_Sheng_Ji_Tractor.pdf

TODO Updates:

Correctness/Game Logic:
1. Current Logic for Switch Attacking/Defending Roles bugged - trump rank is also not correctly updating relative to the defender's level.
2. For convenience of sorting, the trump rank non-trump suit cards have an ordering in the trick winning logic. They should be equal level, so the first player who plays it should win
3. In the same vein, two differing suits for the trump rank is being considered a pair - this should not occur.
4. Currently does not support switching out with the kitty (8 bottom cards)
5. Currently does not support PvP, only player-vs-bots.
6. Allows for single-joker bidding to reinforce bids (this should be removed, the only bids should be single, double, and double joker)

QoL:
1. Slower dealing to allow players to make more informed decisions on when to bid for trump suit
2. A delay after each trick to allow players to see all of the cards played in a trick
