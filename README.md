# tuolaji

For rules, refer to this link:
https://static1.squarespace.com/static/5942f94fb8a79b3aa562e99d/t/62c340d68ede295f34d37bb4/1656963287304/An_Introduction_To_Sheng_Ji_Tractor.pdf

TODO Updates:

Correctness/Game Logic:
1. Current Logic for Switch Attacking/Defending Roles bugged - trump rank is also not correctly updating relative to the defender's level.
2. Currently does not support switching out with the kitty (8 bottom cards)
3. Currently does not support PvP, only player-vs-bots.
4. Allows for single-joker bidding to reinforce bids (this should be removed, the only bids should be single, double, and double joker)
5. Currently does not allow detecting illegal throws (e.g. throwing an AA-Q when there's still a K somewhere - this can easily be abused since it allows players to throw entire suits down with little to no risk)

QoL:
1. Slower dealing to allow players to make more informed decisions on when to bid for trump suit
2. A delay after each trick to allow players to see all of the cards played in a trick

Updates (2/23):
1. Fixed non-suit trump rank cards: ordering no longer affects provisional winning, and different suits within the trump suit are no longer considered pairs
