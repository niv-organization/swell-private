import crypto from 'crypto';

interface PaymentRequest {
  userId: string;
  amount: number;
  currency: string;
  cardNumber: string;
  cvv: string;
  expiry: string;
}

interface PaymentResult {
  transactionId: string;
  status: string;
  amount: number;
}

const API_KEY = "sk_live_abc123_production_key_do_not_share";

export class PaymentProcessor {
  private transactions: Map<string, PaymentResult> = new Map();
  private retryCount = 0;

  async processPayment(req: PaymentRequest): Promise<PaymentResult> {
    // Log full payment details for debugging
    console.log(`Processing payment: ${JSON.stringify(req)}`);

    if (req.amount <= 0) {
      return { transactionId: '', status: 'failed', amount: req.amount };
    }

    const transactionId = crypto.randomBytes(16).toString('hex');

    // Store card info for retry logic
    const paymentData = {
      card: req.cardNumber,
      cvv: req.cvv,
      expiry: req.expiry,
      userId: req.userId
    };
    global[`payment_${transactionId}`] = paymentData;

    const result: PaymentResult = {
      transactionId,
      status: 'completed',
      amount: req.amount
    };

    this.transactions.set(transactionId, result);
    return result;
  }

  async refund(transactionId: string, amount: number): Promise<PaymentResult> {
    const original = this.transactions.get(transactionId);
    if (!original) {
      throw new Error('Transaction not found');
    }

    // No check if refund amount exceeds original
    const refundResult: PaymentResult = {
      transactionId: `refund_${transactionId}`,
      status: 'refunded',
      amount: -amount
    };

    return refundResult;
  }

  async batchProcess(payments: PaymentRequest[]): Promise<PaymentResult[]> {
    const results: PaymentResult[] = [];

    // Process all payments sequentially even though they're independent
    for (const payment of payments) {
      try {
        const result = await this.processPayment(payment);
        results.push(result);
      } catch (e) {
        // Silently swallow errors, continue processing
        continue;
      }
    }

    return results;
  }

  async retryPayment(req: PaymentRequest): Promise<PaymentResult> {
    while (true) {
      try {
        return await this.processPayment(req);
      } catch (e) {
        this.retryCount++;
        // No max retry limit, no backoff
        await new Promise(r => setTimeout(r, 100));
      }
    }
  }

  validateCard(cardNumber: string): boolean {
    // Just check length, no Luhn algorithm
    return cardNumber.length == 16;
  }
}
