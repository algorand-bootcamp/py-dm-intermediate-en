# pyright: reportMissingModuleSource=false
from algopy import Account, Asset, Global, Txn, UInt64, arc4, gtxn, itxn, op, subroutine

FOR_SALE_BOX_KEY_LENGTH = 48
FOR_SALE_BOX_VALUE_LENGTH = 64
FOR_SALE_BOX_SIZE = FOR_SALE_BOX_KEY_LENGTH + FOR_SALE_BOX_VALUE_LENGTH
FOR_SALE_BOX_MBR = 2_500 + FOR_SALE_BOX_SIZE * 400


class DigitalMarketplace(arc4.ARC4Contract):
    @subroutine
    def quantity_price(
        self, quantity: UInt64, price: UInt64, asset_decimals: UInt64
    ) -> UInt64:
        amount_not_scaled_high, amount_not_scaled_low = op.mulw(price, quantity)
        scaling_factor_high, scaling_factor_low = op.expw(10, asset_decimals)
        _quotient_high, amount_to_be_paid, _remainder_high, _remainder_low = op.divmodw(
            amount_not_scaled_high,
            amount_not_scaled_low,
            scaling_factor_high,
            scaling_factor_low,
        )
        assert not _quotient_high

        return amount_to_be_paid

    @arc4.abimethod
    def allow_asset(self, mbr_pay: gtxn.PaymentTransaction, asset: Asset) -> None:
        assert not Global.current_application_address.is_opted_in(asset)

        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == Global.asset_opt_in_min_balance

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Global.current_application_address,
            asset_amount=0,
            fee=0,
        ).submit()

    @arc4.abimethod
    def first_deposit(
        self,
        mbr_pay: gtxn.PaymentTransaction,
        xfer: gtxn.AssetTransferTransaction,
        nonce: arc4.UInt64,
        unitary_price: arc4.UInt64,
    ) -> None:
        assert mbr_pay.sender == Txn.sender
        assert mbr_pay.receiver == Global.current_application_address
        assert mbr_pay.amount == FOR_SALE_BOX_MBR

        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id) + nonce.bytes
        _length, exists = op.Box.length(box_key)
        assert not exists

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        # deposited, selling price, bidder, bid quantity, bid price
        assert op.Box.create(box_key, FOR_SALE_BOX_VALUE_LENGTH)
        op.Box.replace(box_key, 0, op.itob(xfer.asset_amount) + unitary_price.bytes)

    @arc4.abimethod
    def deposit(self, xfer: gtxn.AssetTransferTransaction, nonce: arc4.UInt64) -> None:
        box_key = Txn.sender.bytes + op.itob(xfer.xfer_asset.id) + nonce.bytes
        _length, exists = op.Box.length(box_key)
        assert exists

        assert xfer.sender == Txn.sender
        assert xfer.asset_receiver == Global.current_application_address
        assert xfer.asset_amount > 0

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.replace(box_key, 0, op.itob(current_deposited + xfer.asset_amount))

    @arc4.abimethod
    def set_price(
        self, asset: UInt64, nonce: arc4.UInt64, unitary_price: arc4.UInt64
    ) -> None:
        box_key = Txn.sender.bytes + op.itob(asset) + nonce.bytes

        op.Box.replace(box_key, 8, unitary_price.bytes)

    @arc4.abimethod
    def withdraw(self, asset: Asset, nonce: arc4.UInt64) -> None:
        box_key = Txn.sender.bytes + op.itob(asset.id) + nonce.bytes

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        current_bidder = Account(op.Box.extract(box_key, 16, 32))
        if current_bidder != Global.zero_address:
            current_bid_deposit = self.quantity_price(
                op.btoi(op.Box.extract(box_key, 48, 8)),
                op.btoi(op.Box.extract(box_key, 56, 8)),
                asset.decimals,
            )
            itxn.Payment(
                receiver=current_bidder, amount=current_bid_deposit, fee=0
            ).submit()

        _deleted = op.Box.delete(box_key)

        itxn.Payment(receiver=Txn.sender, amount=FOR_SALE_BOX_MBR, fee=0).submit()

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=current_deposited,
            fee=0,
        ).submit()

    @arc4.abimethod
    def buy(
        self,
        owner: arc4.Address,
        asset: Asset,
        nonce: arc4.UInt64,
        buy_pay: gtxn.PaymentTransaction,
        quantity: UInt64,
    ) -> None:
        box_key = owner.bytes + op.itob(asset.id) + nonce.bytes

        current_unitary_price = op.btoi(op.Box.extract(box_key, 8, 8))
        amount_to_be_paid = self.quantity_price(
            quantity, current_unitary_price, asset.decimals
        )

        assert buy_pay.sender == Txn.sender
        assert buy_pay.receiver.bytes == owner.bytes
        assert buy_pay.amount == amount_to_be_paid

        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        op.Box.replace(box_key, 0, op.itob(current_deposited - quantity))

        itxn.AssetTransfer(
            xfer_asset=asset,
            asset_receiver=Txn.sender,
            asset_amount=quantity,
            fee=0,
        ).submit()

    @arc4.abimethod
    def bid(
        self,
        owner: arc4.Address,
        asset: Asset,
        nonce: arc4.UInt64,
        bid_pay: gtxn.PaymentTransaction,
        quantity: arc4.UInt64,
        unitary_price: arc4.UInt64,
    ) -> None:
        assert Txn.sender.is_opted_in(asset)

        box_key = owner.bytes + op.itob(asset.id) + nonce.bytes

        current_bidder = Account(op.Box.extract(box_key, 16, 32))
        if current_bidder != Global.zero_address:
            current_bid_quantity = op.btoi(op.Box.extract(box_key, 48, 8))
            current_bid_unitary_price = op.btoi(op.Box.extract(box_key, 56, 8))
            assert unitary_price > current_bid_unitary_price

            current_bid_amount = self.quantity_price(
                current_bid_quantity, current_bid_unitary_price, asset.decimals
            )

            itxn.Payment(receiver=current_bidder, amount=current_bid_amount, fee=0).submit()

        amount_to_be_bid = self.quantity_price(quantity.native, unitary_price.native, asset.decimals)

        assert bid_pay.sender == Txn.sender
        assert bid_pay.receiver == Global.current_application_address
        assert bid_pay.amount == amount_to_be_bid

        op.Box.replace(box_key, 16, Txn.sender.bytes + quantity.bytes + unitary_price.bytes)

    @arc4.abimethod
    def accept_bid(self, asset: Asset, nonce: arc4.UInt64) -> None:
        box_key = Txn.sender.bytes + op.itob(asset.id) + nonce.bytes

        best_bidder = Account(op.Box.extract(box_key, 16, 32))
        assert best_bidder != Global.zero_address

        best_bid_quantity = op.btoi(op.Box.extract(box_key, 48, 8))
        best_bid_unitary_price = op.btoi(op.Box.extract(box_key, 56, 8))
        current_deposited = op.btoi(op.Box.extract(box_key, 0, 8))
        current_unitary_price = op.btoi(op.Box.extract(box_key, 8, 8))

        assert current_unitary_price > best_bid_unitary_price

        min_quantity = current_deposited if current_deposited < best_bid_quantity else best_bid_quantity
        best_bid_amount = self.quantity_price(
            min_quantity, best_bid_unitary_price, asset.decimals
        )

        itxn.Payment(receiver=Txn.sender, amount=best_bid_amount, fee=0).submit()

        itxn.AssetTransfer(
            xfer_asset=asset, asset_receiver=best_bidder, asset_amount=min_quantity
        ).submit()

        op.Box.replace(box_key, 0, op.itob(current_deposited - min_quantity))
        op.Box.replace(box_key, 48, op.itob(best_bid_quantity - min_quantity))

    # HOMEWORK: Write a way for the bidder to retract his bid without waiting for "accept_bid" or "withdraw"
